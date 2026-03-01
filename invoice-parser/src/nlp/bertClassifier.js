/**
 * 使用 Transformers.js（@xenova/transformers）加载预训练模型对发票明细文本做分类。
 * 轻量级方案：无训练，用 BERT 抽取向量后与训练集类别质心做余弦相似度，取最大为预测类别。
 *
 * 推荐模型：Xenova/paraphrase-multilingual-MiniLM-L12-v2（多语言含中文、体积较小）
 * 或 Xenova/bert-base-chinese。首次运行会下载模型（约 30MB+）。
 *
 * 生产环境可替换为云端 LLM API。
 */

const { getCategoryName, NUM_CATEGORIES } = require('./categoryLabels');
const trainingData = require('./trainingData.json');

let extractor = null;
let classMeanEmbeddings = null;
const DEFAULT_MODEL = 'Xenova/paraphrase-multilingual-MiniLM-L12-v2';

/**
 * 获取 feature-extraction pipeline（懒加载）
 * 若已准备本地模型，请设置环境变量：
 *   TRANSFORMERS_CACHE=模型根目录（其下需有 Xenova/paraphrase-multilingual-MiniLM-L12-v2/ 及 tokenizer.json、*.onnx 等）
 *   TRANSFORMERS_LOCAL_ONLY=1  仅使用本地文件，不发起网络请求
 * @param {string} [modelId]
 * @param {Object} [opts] - { cache_dir, local_files_only }
 * @returns {Promise<object>}
 */
async function getExtractor(modelId = DEFAULT_MODEL, opts = {}) {
  if (extractor) return extractor;
  const { pipeline, env } = require('@xenova/transformers');
  const cacheDir = opts.cache_dir || process.env.TRANSFORMERS_CACHE;
  const localOnly = opts.local_files_only != null
    ? opts.local_files_only
    : (process.env.TRANSFORMERS_LOCAL_ONLY === '1' || process.env.TRANSFORMERS_LOCAL_ONLY === 'true');
  if (cacheDir && typeof env.localModelPath !== 'undefined') {
    env.localModelPath = cacheDir;
  }
  extractor = await pipeline('feature-extraction', modelId, {
    quantized: true,
    ...(cacheDir && { cache_dir: cacheDir }),
    ...(localOnly && { local_files_only: true }),
  });
  return extractor;
}

/**
 * 将模型输出转为 1D 向量（mean pooling + 展平）
 * @param {any} output - pipeline 返回的 tensor 或 nested array
 * @returns {number[]}
 */
function toVector(output) {
  if (!output) return [];
  if (Array.isArray(output)) {
    const flat = (arr) => arr.reduce((acc, x) => acc.concat(Array.isArray(x) ? flat(x) : [x]), []);
    return flat(output);
  }
  if (typeof output.data === 'function') {
    const d = output.data();
    return Array.from(d && d.length != null ? d : []);
  }
  if (output.data && typeof output.data.length === 'number') {
    return Array.from(output.data);
  }
  if (output.dims && output.dims.length >= 1) {
    const size = output.dims.reduce((a, b) => a * b, 1);
    const d = output.data;
    const arr = typeof d === 'function' ? d() : d;
    return arr ? Array.from(arr).slice(0, size) : [];
  }
  return [];
}

/**
 * 余弦相似度
 * @param {number[]} a
 * @param {number[]} b
 * @returns {number}
 */
function cosineSimilarity(a, b) {
  if (a.length !== b.length || a.length === 0) return 0;
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom <= 0 ? 0 : dot / denom;
}

/**
 * 计算并缓存每个类别的平均向量（按 trainingData 的 label 分组求均）
 * @returns {Promise<number[][]>}
 */
async function getClassMeanEmbeddings() {
  if (classMeanEmbeddings) return classMeanEmbeddings;
  const pipe = await getExtractor();
  const byClass = {};
  for (const { text, label } of trainingData) {
    if (!byClass[label]) byClass[label] = [];
    byClass[label].push(text);
  }
  const means = [];
  for (let c = 0; c < NUM_CATEGORIES; c++) {
    const texts = byClass[c] || [];
    if (texts.length === 0) {
      means.push(null);
      continue;
    }
    const vecs = [];
    for (const t of texts) {
      const out = await pipe(t, { pooling: 'mean', normalize: true });
      vecs.push(toVector(out));
    }
    const dim = vecs[0]?.length || 0;
    const sum = new Array(dim).fill(0);
    for (const v of vecs) {
      for (let i = 0; i < dim; i++) sum[i] += v[i] || 0;
    }
    const n = vecs.length;
    for (let i = 0; i < dim; i++) sum[i] /= n;
    means.push(sum);
  }
  classMeanEmbeddings = means;
  return classMeanEmbeddings;
}

/**
 * 使用 BERT 对发票明细文本分类（无训练，基于与训练集类别质心的相似度）
 * @param {string} text - 发票明细文本
 * @param {Object} [options]
 * @param {string} [options.modelId] - 模型 ID
 * @returns {Promise<{ category: number, categoryName: string, confidence: number }>}
 */
async function classifyWithBERT(text, options = {}) {
  const normalized = (text != null ? String(text).trim() : '') || '';
  if (!normalized) {
    return { category: 9, categoryName: getCategoryName(9), confidence: 0 };
  }
  const pipe = await getExtractor(options.modelId, options);
  const means = await getClassMeanEmbeddings();
  const out = await pipe(normalized, { pooling: 'mean', normalize: true });
  const vec = toVector(out);
  let best = 9;
  let bestSim = -1;
  for (let c = 0; c < NUM_CATEGORIES; c++) {
    if (!means[c] || means[c].length !== vec.length) continue;
    const sim = cosineSimilarity(vec, means[c]);
    if (sim > bestSim) {
      bestSim = sim;
      best = c;
    }
  }
  const confidence = Math.max(0, Math.min(1, bestSim));
  return {
    category: best,
    categoryName: getCategoryName(best),
    confidence,
  };
}

/**
 * 重置缓存（用于换模型或重载训练数据）
 */
function resetCache() {
  extractor = null;
  classMeanEmbeddings = null;
}

module.exports = {
  classifyWithBERT,
  getExtractor,
  getClassMeanEmbeddings,
  resetCache,
  toVector,
  cosineSimilarity,
};
