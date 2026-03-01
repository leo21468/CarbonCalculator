/**
 * 发票解析引擎统一入口
 * 根据 fileType 调度 OFD/PDF/XML/JSON 解析器，返回统一 Invoice 对象
 * 带错误处理与简单日志
 */

const path = require('path');
const fs = require('fs');
const { Invoice } = require('../models/Invoice');
const { parseOfdFile } = require('./ofdParser');
const { parsePdfFile } = require('./pdfParser');
const { parseXmlFile } = require('./xmlParser');
const { parseJsonFile } = require('./jsonParser');

/** 支持的扩展名与类型映射 */
const EXT_TO_TYPE = {
  '.ofd': 'OFD',
  '.pdf': 'PDF',
  '.xml': 'XML',
  '.json': 'JSON',
};

/** 日志前缀 */
const LOG_PREFIX = '[InvoiceParser]';

/**
 * 简单日志
 * @param {string} level - 'info' | 'warn' | 'error'
 * @param {string} message
 * @param {Error} [err]
 */
function log(level, message, err) {
  const ts = new Date().toISOString();
  const msg = err ? `${message} ${err.message}` : message;
  const line = `${ts} ${LOG_PREFIX} ${level.toUpperCase()} ${msg}`;
  if (level === 'error' && err && err.stack) {
    console.error(line);
    console.error(err.stack);
  } else if (level === 'error') {
    console.error(line);
  } else if (level === 'warn') {
    console.warn(line);
  } else {
    console.log(line);
  }
}

/**
 * 根据路径或传入类型解析发票
 * @param {string} filePath - 发票文件路径
 * @param {string} [fileType] - 可选，文件类型：OFD | PDF | XML | JSON。不传则按扩展名推断
 * @returns {Promise<Invoice>} 统一发票对象
 * @throws 文件不存在或解析失败时抛出 Error
 */
async function parseInvoice(filePath, fileType) {
  const resolved = path.resolve(filePath);
  const ext = path.extname(resolved).toLowerCase();
  const type = (fileType && fileType.toUpperCase()) || EXT_TO_TYPE[ext] || null;

  if (!type || !['OFD', 'PDF', 'XML', 'JSON'].includes(type)) {
    const err = new Error(`不支持的文件类型: ${ext || fileType}，支持: OFD, PDF, XML, JSON`);
    log('error', 'parseInvoice', err);
    throw err;
  }

  try {
    const stat = await fs.promises.stat(resolved);
    if (!stat.isFile()) {
      const err = new Error(`路径不是文件: ${resolved}`);
      log('error', 'parseInvoice', err);
      throw err;
    }
  } catch (e) {
    if (e.code === 'ENOENT') {
      const err = new Error(`文件不存在: ${resolved}`);
      log('error', 'parseInvoice', err);
      throw err;
    }
    log('error', 'parseInvoice', e);
    throw e;
  }

  log('info', `开始解析 ${type} 文件: ${resolved}`);

  try {
    let invoice;
    switch (type) {
      case 'OFD':
        invoice = await parseOfdFile(resolved);
        break;
      case 'PDF':
        invoice = await parsePdfFile(resolved);
        break;
      case 'XML':
        invoice = await parseXmlFile(resolved);
        break;
      case 'JSON':
        invoice = await parseJsonFile(resolved);
        break;
      default:
        throw new Error(`未实现的解析器: ${type}`);
    }

    if (!(invoice instanceof Invoice)) {
      throw new Error('解析器未返回 Invoice 实例');
    }
    invoice.fileType = type;
    log('info', `解析完成: ${resolved}`);
    return invoice;
  } catch (e) {
    log('error', `解析失败 ${resolved}`, e);
    throw e;
  }
}

module.exports = {
  parseInvoice,
  Invoice,
  log,
  EXT_TO_TYPE,
};

// 子解析器按需导出
module.exports.parseOfdFile = parseOfdFile;
module.exports.parsePdfFile = parsePdfFile;
module.exports.parseXmlFile = parseXmlFile;
module.exports.parseJsonFile = parseJsonFile;
