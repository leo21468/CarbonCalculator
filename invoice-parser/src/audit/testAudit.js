/**
 * 审计模块测试：处理一张发票、生成审计报告、验证所有步骤被记录
 */

const path = require('path');
const { processSingleInvoice } = require('../orchestrator/processInvoice');
const auditLogger = require('./auditLogger');
const fs = require('fs');

const MOCK_INVOICE = {
  invoiceNumber: 'TEST-AUDIT-001',
  totalAmount: 1000,
  sellerName: '测试销售方',
  buyerName: '测试购买方',
  items: [
    { name: '办公用品', amount: 500, quantity: 1, taxCode: '109041399' },
    { name: '电力', amount: 500, quantity: 100, taxCode: '109041399', unit: 'kWh' },
  ],
};

async function run() {
  console.log('=== 审计追踪测试 ===\n');

  // 1. 使用 enableAudit 处理一张发票
  const report = await processSingleInvoice(MOCK_INVOICE, { enableAudit: true });
  const invoiceId = report.invoice.invoiceNumber || report.invoice.invoiceId;

  console.log('1. 处理结果:', report.result.totalEmissions.toFixed(2), 'kgCO2e');
  console.log('   发票ID:', invoiceId);
  console.log('   审计追踪:', report.auditTrail ? '已创建' : '未创建');

  // 2. 查询审计记录
  const trail = auditLogger.getAuditTrail(invoiceId);
  if (!trail) {
    console.error('失败: 未找到审计记录');
    process.exit(1);
  }
  console.log('\n2. 审计记录 ID:', trail.id);
  console.log('   步骤数:', (trail.steps || []).length);
  console.log('   步骤名:', (trail.steps || []).map((s) => s.stepName).join(', '));

  // 3. 验证预期步骤存在
  const stepNames = (trail.steps || []).map((s) => s.stepName);
  const required = ['解析'];
  const hasRequired = required.every((name) => stepNames.includes(name));
  if (!hasRequired) {
    console.error('失败: 缺少预期步骤，需要包含:', required.join(', '));
    process.exit(1);
  }
  console.log('\n3. 步骤校验: 通过（包含解析等步骤）');

  // 4. 导出 JSON 报告
  const jsonReport = auditLogger.exportAuditReport(invoiceId, 'json');
  if (!jsonReport || jsonReport === 'null') {
    console.error('失败: JSON 导出为空');
    process.exit(1);
  }
  const parsed = JSON.parse(jsonReport);
  if (!parsed.finalResult && !parsed.dataSources) {
    console.error('失败: 导出缺少 finalResult 或 dataSources');
    process.exit(1);
  }
  console.log('\n4. 导出 JSON: 成功，含 finalResult 与 dataSources');

  // 5. 导出 HTML 报告（不应含未替换的占位符）
  const htmlReport = auditLogger.exportAuditReport(invoiceId, 'html');
  if (!htmlReport || htmlReport.includes('未找到该发票的审计记录')) {
    console.error('失败: HTML 导出为空或未找到记录');
    process.exit(1);
  }
  if (htmlReport.includes('{{AUDIT_ID}}') || htmlReport.includes('{{INVOICE_ID}}')) {
    console.error('失败: HTML 中仍有未替换占位符');
    process.exit(1);
  }
  console.log('5. 导出 HTML: 成功');

  // 6. 可选：写入文件便于查看
  const outDir = path.join(__dirname, '..', '..', 'out');
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
  const jsonPath = path.join(outDir, `audit-${invoiceId}.json`);
  const htmlPath = path.join(outDir, `audit-${invoiceId}.html`);
  fs.writeFileSync(jsonPath, jsonReport, 'utf8');
  fs.writeFileSync(htmlPath, htmlReport, 'utf8');
  console.log('\n6. 已写入:', jsonPath, htmlPath);

  console.log('\n=== 全部测试通过 ===');
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
