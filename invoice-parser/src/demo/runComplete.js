/**
 * 完整碳核算流程演示：10 张模拟发票，执行完整处理，输出分 Scope 报表与置信度统计
 */

const path = require('path');
const { processSingleInvoice, processBatchInvoice } = require('../orchestrator/processInvoice');
const { confidenceReport } = require('../orchestrator/confidenceReporter');

/** 10 张模拟发票（无文件，直接对象） */
const MOCK_INVOICES = [
  { invoiceNumber: 'INV-E-001', items: [{ name: '电费', quantity: 10000, unit: 'kWh', amount: 6000 }], totalAmount: 6000, sellerName: '国网上海市电力公司' },
  { invoiceNumber: 'INV-W-002', items: [{ name: '水费', quantity: 100, unit: '吨', amount: 500 }], totalAmount: 500, sellerName: '上海市自来水公司' },
  { invoiceNumber: 'INV-H-003', items: [{ name: '住宿费', amount: 1200 }], totalAmount: 1200, sellerName: '上海某酒店有限公司', remark: '住宿2晚' },
  { invoiceNumber: 'INV-O-004', items: [{ name: '办公用品', amount: 5000 }], totalAmount: 5000, sellerName: '某文具公司' },
  { invoiceNumber: 'INV-F-005', items: [{ name: '汽油', quantity: 50, unit: '升', amount: 400 }], totalAmount: 400, sellerName: '某加油站' },
  { invoiceNumber: 'INV-T-006', items: [{ name: '一卡通充值', amount: 200 }], totalAmount: 200, sellerName: '某公交公司' },
  { invoiceNumber: 'INV-L-007', items: [{ name: '物流运输费', amount: 1500 }], totalAmount: 1500, sellerName: '某物流公司' },
  { invoiceNumber: 'INV-G-008', items: [{ name: '垃圾清运费', amount: 800 }], totalAmount: 800, sellerName: '某环卫公司' },
  { invoiceNumber: 'INV-S-009', items: [{ name: '冷轧钢板', quantity: 20, unit: '吨', amount: 100000 }], totalAmount: 100000, sellerName: '某钢铁公司' },
  { invoiceNumber: 'INV-X-010', items: [{ name: '杂项费用', amount: 3000 }], totalAmount: 3000, sellerName: '某服务公司' },
];

async function run() {
  console.log('========== 完整碳核算流程演示 ==========\n');
  console.log('处理 10 张模拟发票...\n');

  const { results, summary, reports } = await processBatchInvoice(MOCK_INVOICES);

  // 分 Scope 汇总
  console.log('---------- 分 Scope 汇总 ----------');
  console.log(`  Scope 1（直接排放）: ${summary.scope1.toFixed(2)} kgCO2e`);
  console.log(`  Scope 2（能源间接）: ${summary.scope2.toFixed(2)} kgCO2e`);
  console.log(`  Scope 3（价值链其他）: ${summary.scope3.toFixed(2)} kgCO2e`);
  console.log(`  总排放: ${summary.totalEmissions.toFixed(2)} kgCO2e`);
  console.log(`  发票数: ${summary.invoiceCount}\n`);

  // 置信度统计（合并所有 result.items）
  const allItems = results.flatMap((r) => r.items || []);
  const report = confidenceReport({ items: allItems });
  console.log('---------- 置信度统计 ----------');
  console.log(`  高: ${report.counts.high} 条`);
  console.log(`  中: ${report.counts.medium} 条`);
  console.log(`  低: ${report.counts.low} 条`);
  console.log(`  合计: ${report.counts.total} 条`);
  if (report.needReview.needReview.length > 0) {
    console.log('\n  需人工复核（低置信度）:');
    report.needReview.needReview.forEach((r, i) => {
      console.log(`    ${i + 1}. [${r.invoiceId}] ${r.itemName || '-'} ${r.emissions != null ? r.emissions.toFixed(2) + ' kgCO2e' : ''} - ${r.reason || ''}`);
    });
  }

  // 每张发票简要结果
  console.log('\n---------- 单张发票结果 ----------');
  reports.forEach((rep, i) => {
    const inv = rep.invoice?.invoiceNumber || MOCK_INVOICES[i]?.invoiceNumber || i + 1;
    const total = rep.result.totalEmissions.toFixed(2);
    const scope = rep.result.summary ? `S1:${rep.result.summary.scope1.toFixed(0)} S2:${rep.result.summary.scope2.toFixed(0)} S3:${rep.result.summary.scope3.toFixed(0)}` : '-';
    console.log(`  ${inv}  总排放: ${total} kgCO2e  (${scope})`);
  });

  console.log('\n========== 演示结束 ==========');
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
