/**
 * 碳核算 API 服务
 *
 * - POST /api/upload  上传单张发票
 * - POST /api/batch   批量上传
 * - GET  /api/report/:id  获取报告
 */

const express = require('express');
const multer = require('multer');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { processSingleInvoice } = require('../orchestrator/processInvoice');
const { confidenceReport } = require('../orchestrator/confidenceReporter');

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

/** 报告存储（内存 Map，生产可换 Redis/DB） */
const reportStore = new Map();
let reportIdCounter = 1;

const uploadDir = path.join(os.tmpdir(), 'carbon-invoice-upload');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadDir),
  filename: (req, file, cb) => cb(null, `${Date.now()}-${Math.random().toString(36).slice(2)}${path.extname(file.originalname) || ''}`),
});
const upload = multer({ storage });

/**
 * POST /api/upload  单张发票上传（multipart/form-data 字段名: file）
 * 或 POST /api/upload  body 为 JSON 发票对象 { items, totalAmount, ... }
 */
app.post('/api/upload', (req, res) => {
  const run = async (invoiceInput) => {
    const { result, invoice, logs } = await processSingleInvoice(invoiceInput);
    const id = String(reportIdCounter++);
    const conf = confidenceReport(result);
    reportStore.set(id, {
      id,
      result: result.toObject ? result.toObject() : result,
      invoice: invoice || null,
      logs,
      confidence: conf,
      createdAt: new Date().toISOString(),
    });
    return id;
  };

  if (req.is('application/json') && req.body && (req.body.items || req.body.invoiceNumber)) {
    run(req.body)
      .then((id) => res.status(201).json({ id, message: '已处理' }))
      .catch((e) => res.status(500).json({ error: e.message }));
    return;
  }

  upload.single('file')(req, res, async (err) => {
    if (err) return res.status(400).json({ error: err.message });
    const file = req.file;
    if (!file) return res.status(400).json({ error: '请上传文件或提交 JSON 发票' });
    try {
      const id = await run(file.path);
      try { fs.unlinkSync(file.path); } catch (_) {}
      res.status(201).json({ id, message: '已处理' });
    } catch (e) {
      try { if (file && file.path) fs.unlinkSync(file.path); } catch (_) {}
      res.status(500).json({ error: e.message });
    }
  });
});

/**
 * POST /api/batch  批量上传（multipart 多文件 field: files）或 JSON 数组
 */
app.post('/api/batch', (req, res) => {
  const run = async (inputs) => {
    const { processBatchInvoice } = require('../orchestrator/processInvoice');
    const { results, summary, reports } = await processBatchInvoice(inputs);
    const id = String(reportIdCounter++);
    const allItems = results.flatMap((r) => r.items || []);
    const conf = confidenceReport({ items: allItems });
    reportStore.set(id, {
      id,
      results: results.map((r) => r.toObject ? r.toObject() : r),
      summary,
      reports: reports.map((r) => ({ result: r.result.toObject ? r.result.toObject() : r.result, logs: r.logs })),
      confidence: conf,
      createdAt: new Date().toISOString(),
    });
    return id;
  };

  if (req.is('application/json') && Array.isArray(req.body)) {
    run(req.body)
      .then((id) => res.status(201).json({ id, message: '批量处理完成' }))
      .catch((e) => res.status(500).json({ error: e.message }));
    return;
  }

  upload.array('files', 20)(req, res, async (err) => {
    if (err) return res.status(400).json({ error: err.message });
    const files = req.files || [];
    if (files.length === 0) return res.status(400).json({ error: '请上传至少一个文件' });
    const paths = files.map((f) => f.path);
    try {
      const id = await run(paths);
      paths.forEach((p) => { try { fs.unlinkSync(p); } catch (_) {} });
      res.status(201).json({ id, message: `已处理 ${files.length} 张发票` });
    } catch (e) {
      paths.forEach((p) => { try { fs.unlinkSync(p); } catch (_) {} });
      res.status(500).json({ error: e.message });
    }
  });
});

/**
 * GET /api/report/:id  获取报告
 */
app.get('/api/report/:id', (req, res) => {
  const rec = reportStore.get(req.params.id);
  if (!rec) return res.status(404).json({ error: '报告不存在' });
  res.json(rec);
});

/** 健康检查 */
app.get('/api/health', (req, res) => res.json({ status: 'ok' }));

function start(port = 3000) {
  return app.listen(port, () => {
    console.log(`Carbon API 已启动: http://localhost:${port}`);
    console.log('  POST /api/upload  上传单张发票');
    console.log('  POST /api/batch  批量上传');
    console.log('  GET  /api/report/:id  获取报告');
  });
}

module.exports = { app, start };

if (require.main === module) {
  start(process.env.PORT || 3000);
}
