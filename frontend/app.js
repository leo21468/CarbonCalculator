/**
 * 碳足迹 Agent 前端脚本
 * 模块：ApiClient（统一请求）、UI（DOM操作）、Toast、debounce、CSV导出、localStorage历史
 */
(function () {
  'use strict';

  const API = window.location.origin;
  const HISTORY_KEY = 'carbon_query_history';
  const HISTORY_MAX = 5;

  // ─── 工具函数 ─────────────────────────────────────────────
  function debounce(fn, delay) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  function $(id) { return document.getElementById(id); }

  // ─── Toast 通知系统 ───────────────────────────────────────
  const Toast = {
    show(msg, type = 'info', duration = 3000) {
      let container = $('toast-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
      }
      const el = document.createElement('div');
      el.className = `toast ${type}`;
      el.textContent = msg;
      container.appendChild(el);
      setTimeout(() => { el.remove(); }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg)   { this.show(msg, 'error', 4000); },
    info(msg)    { this.show(msg, 'info'); },
  };

  // ─── ApiClient ────────────────────────────────────────────
  const ApiClient = {
    async request(method, path, body, btnEl) {
      if (btnEl) this._setLoading(btnEl, true);
      try {
        const opts = {
          method,
          headers: body && !(body instanceof FormData) ? { 'Content-Type': 'application/json' } : {},
          body: body ? (body instanceof FormData ? body : JSON.stringify(body)) : undefined,
        };
        const res = await fetch(API + path, opts);
        const text = await res.text();
        let data;
        try { data = text ? JSON.parse(text) : {}; }
        catch (_) { throw new Error('服务器返回非 JSON 响应'); }
        if (!res.ok) throw new Error(data.detail || data.error || '请求失败');
        return data;
      } finally {
        if (btnEl) this._setLoading(btnEl, false);
      }
    },
    _setLoading(btn, loading) {
      if (loading) {
        btn._origText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner"></span>处理中...';
        btn.disabled = true;
      } else {
        btn.innerHTML = btn._origText || btn.innerHTML;
        btn.disabled = false;
      }
    },
    get(path)         { return this.request('GET', path); },
    post(path, body, btn) { return this.request('POST', path, body, btn); },
    put(path, body)   { return this.request('PUT', path, body); },
    del(path)         { return this.request('DELETE', path); },
  };

  // ─── localStorage 历史记录 ────────────────────────────────
  const History = {
    load() {
      try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
      catch (_) { return []; }
    },
    save(list) {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, HISTORY_MAX)));
    },
    add(term) {
      if (!term) return;
      const list = this.load().filter(x => x !== term);
      list.unshift(term);
      this.save(list);
    },
    render(containerEl, onSelect) {
      const list = this.load();
      if (!list.length) { containerEl.innerHTML = ''; return; }
      const ul = document.createElement('ul');
      ul.className = 'history-list';
      list.forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        li.addEventListener('click', () => onSelect(item));
        ul.appendChild(li);
      });
      containerEl.innerHTML = '';
      containerEl.appendChild(ul);
    },
  };

  // ─── CSV 导出 ─────────────────────────────────────────────
  function exportCSV(rows, headers, filename) {
    const escape = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [headers.map(escape).join(',')];
    rows.forEach(row => lines.push(row.map(escape).join(',')));
    const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ─── 确认对话框 ───────────────────────────────────────────
  function confirm(msg) {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.className = 'dialog-overlay';
      overlay.innerHTML = `
        <div class="dialog-box">
          <h3>确认操作</h3>
          <p>${msg}</p>
          <div class="dialog-actions">
            <button class="secondary" id="dlg-cancel">取消</button>
            <button class="danger" id="dlg-ok">确认</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.querySelector('#dlg-ok').addEventListener('click', () => { overlay.remove(); resolve(true); });
      overlay.querySelector('#dlg-cancel').addEventListener('click', () => { overlay.remove(); resolve(false); });
    });
  }

  // ─── 辅助：获取响应中的 data 字段（兼容新旧格式）─────────
  function unwrap(body) {
    return ('data' in body) ? body.data : body;
  }

  // ─── 健康检查 ─────────────────────────────────────────────
  async function checkHealth() {
    const el = $('apiStatus');
    try {
      const data = await ApiClient.get('/api/health');
      el.textContent = (data.service || '服务') + ' 运行正常';
      el.className = 'api-status ok';
    } catch (_) {
      el.textContent = '无法连接后端，请确认已运行 python run_server.py';
      el.className = 'api-status err';
    }
  }

  // ─── 标签页切换 ───────────────────────────────────────────
  function initTabs() {
    document.querySelectorAll('.main-tabs button').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.main-tabs button').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('show'));
        btn.classList.add('active');
        $('panel-' + btn.dataset.tab).classList.add('show');
        if (btn.dataset.tab === 'manage') loadProductList();
        if (btn.dataset.tab === 'stats')  loadStats();
      });
    });
  }

  // ─── 面板1：产品查询 ──────────────────────────────────────
  function initQueryPanel() {
    const input    = $('productInput');
    const btnQuery = $('btnQuery');
    const btnClear = $('btnClear');
    const resultEl = $('result');
    const historyEl = $('queryHistory');

    function scopeClass(scope) {
      if (!scope) return '';
      if (scope.includes('1')) return 'scope1';
      if (scope.includes('2')) return 'scope2';
      return 'scope3';
    }

    function showResult(body) {
      const data = unwrap(body);
      if (!data || data.source === 'none') {
        resultEl.innerHTML = `<p class="error-msg">${(body && body.message) || data && data.message || '未找到匹配'}</p>`;
        return;
      }
      const tag = data.source === 'custom' ? 'custom' : 'cpcd';
      const sc = scopeClass(data.carbon_type);
      const rows = [
        ['来源', `<span class="source-tag ${tag}">${data.source === 'custom' ? '自定义' : 'CPCD'}</span>`],
        ['产品名称', data.product_name],
        ['碳种类', `<span class="scope-tag ${sc}">${data.carbon_type}</span>`],
        ['碳足迹', data.carbon_footprint || '-'],
        ['CO2当量 (kg/单位)', data.co2_per_unit_kg != null ? data.co2_per_unit_kg : '-'],
        ['单位', data.unit || '-'],
        ['碳成本 (元/单位)', data.carbon_cost_cny != null ? '¥' + data.carbon_cost_cny : '-'],
      ];
      if (data.similarity != null) rows.splice(1, 0, ['相似度', data.similarity]);
      resultEl.innerHTML = rows.map(([k, v]) =>
        `<div class="result-item"><span class="k">${k}</span><span class="v">${v}</span></div>`
      ).join('');
    }

    async function doQuery() {
      const name = input.value.trim();
      if (!name) {
        resultEl.innerHTML = '<p class="error-msg">请输入产品名称</p>';
        input.classList.add('input-error');
        return;
      }
      input.classList.remove('input-error');
      resultEl.innerHTML = '查询中...';
      try {
        const body = await ApiClient.post('/api/match', { product_name: name }, btnQuery);
        showResult(body);
        History.add(name);
        History.render(historyEl, val => { input.value = val; doQuery(); });
      } catch (e) {
        resultEl.innerHTML = `<p class="error-msg">${e.message}</p>`;
        Toast.error(e.message);
      }
    }

    btnQuery.addEventListener('click', doQuery);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') doQuery(); });
    btnClear.addEventListener('click', () => { resultEl.innerHTML = ''; });

    // 防抖自动建议（300ms）
    const debouncedHint = debounce(async () => {
      const name = input.value.trim();
      if (!name || name.length < 2) return;
    }, 300);
    input.addEventListener('input', debouncedHint);

    // 恢复历史
    History.render(historyEl, val => { input.value = val; doQuery(); });
  }

  // ─── 面板2：发票分析 ──────────────────────────────────────
  function initInvoicePanel() {
    const invoiceResult = $('invoiceResult');

    function scopeClass(scope) {
      if (!scope) return '';
      if (scope.includes('1')) return 'scope1';
      if (scope.includes('2')) return 'scope2';
      return 'scope3';
    }

    function showInvoiceResult(body) {
      const data = unwrap(body);
      const msg  = body.message || '';
      let html = `<p style="color:var(--success);margin-bottom:0.75rem;">✓ ${msg}</p>`;
      if (data.invoice_number || data.seller) {
        html += '<div style="margin-bottom:0.75rem;font-size:0.9rem;color:var(--muted);">';
        if (data.invoice_number) html += `发票号码：${data.invoice_number}　`;
        if (data.seller) html += `销方：${data.seller}`;
        html += '</div>';
      }
      if (data.total_emissions_kg != null) {
        html += `<div class="stat-card" style="margin-bottom:0.75rem;">
          <div class="label">总排放</div>
          <div class="value">${data.total_emissions_kg} kgCO2e</div>
        </div>`;
      }
      if (data.aggregate) {
        html += '<div class="stats-grid">';
        for (const [scope, kg] of Object.entries(data.aggregate)) {
          const kgNum = Number(kg);
          const kgStr = (kgNum === 0 && !data.total_emissions_kg) ? '0' : (Number.isInteger(kgNum) ? kgNum : kgNum.toFixed(4));
          html += `<div class="stat-card"><div class="label">${scope}</div><div class="value">${kgStr} kg</div></div>`;
        }
        html += '</div>';
        if (data.total_emissions_kg === 0) {
          if (!data.lines || data.lines.length === 0) {
            html += '<p class="hint" style="margin-top:0.5rem;color:var(--muted);font-size:0.9rem;">未计算出排放量：所有明细已被过滤（如金额为 0 或表头行）。请确认 PDF 解析出的「金额」列是否正确。</p>';
          } else {
            const allZero = data.lines.every(l => !l.emission_kg || l.emission_kg === 0);
            if (allZero) {
              html += '<p class="hint" style="margin-top:0.5rem;color:var(--muted);font-size:0.9rem;">未计算出排放量：请检查发票明细中的「金额」是否已正确解析（金额需大于 0）。</p>';
            }
          }
        }
      }
      if (data.lines && data.lines.length) {
        html += '<table class="category-table"><tr><th>名称</th><th>范围</th><th>匹配方式</th><th>金额</th><th>排放(kg)</th></tr>';
        for (const l of data.lines) {
          const nameOneLine = (l.name || '').replace(/\s+/g, ' ').trim();
          html += `<tr><td>${nameOneLine}</td>
            <td><span class="scope-tag ${scopeClass(l.scope)}">${l.scope}</span></td>
            <td>${l.match_type}</td><td>¥${l.amount}</td><td>${l.emission_kg}</td></tr>`;
        }
        html += '</table>';
        html += `<button class="secondary" style="margin-top:0.75rem;" id="btnExportInvoice">导出 CSV</button>`;
      }
      invoiceResult.innerHTML = html;

      const btn = $('btnExportInvoice');
      if (btn) {
        btn.addEventListener('click', () => {
          exportCSV(
            data.lines.map(l => [(l.name || '').replace(/\s+/g, ' ').trim(), l.scope, l.match_type, l.amount, l.emission_kg, l.tax_code || '']),
            ['名称', '范围', '匹配方式', '金额', '排放(kg)', '税收编码'],
            'invoice_result.csv'
          );
        });
      }
    }

    // PDF 上传
    document.querySelectorAll('[data-invoice-mode]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-invoice-mode]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const isJson = btn.dataset.invoiceMode === 'json';
        $('invoiceFileSection').style.display = isJson ? 'none' : 'block';
        $('invoiceJsonSection').style.display = isJson ? 'block' : 'none';
      });
    });

    $('invoiceForm').addEventListener('submit', async e => {
      e.preventDefault();
      const fileInput = $('invoiceFile');
      if (!fileInput.files || !fileInput.files.length) {
        invoiceResult.innerHTML = '<p class="error-msg">请选择发票文件（PDF / XML / OFD）</p>';
        return;
      }
      const fd = new FormData();
      fd.append('file', fileInput.files[0]);
      invoiceResult.innerHTML = '解析中，请稍候...';
      const btn = $('btnUpload');
      try {
        const body = await ApiClient.post('/api/invoice/upload', fd, btn);
        showInvoiceResult(body);
        Toast.success('发票解析完成');
      } catch (e) {
        invoiceResult.innerHTML = `<p class="error-msg">${e.message}</p>`;
        Toast.error(e.message);
      }
    });

    // JSON 提交
    $('btnSubmitJson').addEventListener('click', async () => {
      const raw = $('invoiceJsonInput').value.trim();
      if (!raw) { invoiceResult.innerHTML = '<p class="error-msg">请输入发票 JSON</p>'; return; }
      let body;
      try { body = JSON.parse(raw); }
      catch (e) { invoiceResult.innerHTML = `<p class="error-msg">JSON 格式错误：${e.message}</p>`; return; }
      if (!body.lines && !body.items) {
        invoiceResult.innerHTML = '<p class="error-msg">JSON 需包含 lines 或 items 数组</p>';
        return;
      }
      invoiceResult.innerHTML = '处理中...';
      const btn = $('btnSubmitJson');
      try {
        const resp = await ApiClient.post('/api/invoice/process', body, btn);
        showInvoiceResult(resp);
        Toast.success('发票核算完成');
      } catch (e) {
        invoiceResult.innerHTML = `<p class="error-msg">${e.message}</p>`;
        Toast.error(e.message);
      }
    });
  }

  // ─── 面板3：数据管理（新增产品）─────────────────────────────
  function initManagePanel() {
    const addForm = $('addForm');
    const addMsg  = $('addMsg');

    addForm.addEventListener('submit', async e => {
      e.preventDefault();
      const fd = new FormData(addForm);
      const nameVal = fd.get('product_name') || '';
      const nameInput = addForm.querySelector('[name=product_name]');
      const nameErr   = $('errProductName');
      if (!nameVal.trim()) {
        nameInput.classList.add('input-error');
        nameErr.classList.add('show');
        return;
      }
      nameInput.classList.remove('input-error');
      nameErr.classList.remove('show');

      const body = {
        product_name: nameVal,
        carbon_type: fd.get('carbon_type'),
        carbon_footprint: fd.get('carbon_footprint') || '',
        co2_per_unit: parseFloat(fd.get('co2_per_unit')),
        unit: fd.get('unit'),
        price_per_ton: parseFloat(fd.get('price_per_ton')) || 100,
        remark: fd.get('remark') || '',
      };
      addMsg.innerHTML = '';
      const btn = addForm.querySelector('button[type=submit]');
      try {
        await ApiClient.post('/api/products', body, btn);
        addMsg.innerHTML = '<span style="color:var(--success)">✓ 添加成功</span>';
        addForm.reset();
        Toast.success('产品添加成功');
      } catch (e) {
        addMsg.innerHTML = `<span class="error-msg">${e.message}</span>`;
        Toast.error(e.message);
      }
    });
  }

  // ─── 面板3：产品列表 ─────────────────────────────────────
  let _productCache = [];
  let _sortField = null;
  let _sortAsc = true;

  async function loadProductList(nameFilter) {
    const el = $('productList');
    el.innerHTML = '加载中...';
    try {
      const qs = nameFilter ? `?product_name=${encodeURIComponent(nameFilter)}` : '';
      const body = await ApiClient.get('/api/products' + qs);
      _productCache = unwrap(body) || [];
      renderProductList();
    } catch (e) {
      el.innerHTML = '加载失败';
      Toast.error('产品列表加载失败：' + e.message);
    }
  }

  function renderProductList() {
    const el = $('productList');
    let list = [..._productCache];
    if (_sortField) {
      list.sort((a, b) => {
        const av = a[_sortField], bv = b[_sortField];
        return _sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
      });
    }
    if (!list.length) { el.innerHTML = '<p style="color:var(--muted);padding:0.5rem;">暂无自定义数据</p>'; return; }
    el.innerHTML = list.map(p => `
      <div class="product-item" data-id="${p.id}">
        <span class="info" title="${p.product_name} | ${p.carbon_type} | ${p.carbon_footprint || '-'} | ${p.co2_per_unit} kg/${p.unit}">
          <strong>${p.product_name}</strong>
          <span style="color:var(--muted);margin-left:0.5rem;">${p.carbon_type}</span>
          <span style="color:var(--success);margin-left:0.5rem;">${p.co2_per_unit} kg/${p.unit}</span>
        </span>
        <span class="actions">
          <button class="secondary btn-delete-product" data-id="${p.id}">删除</button>
        </span>
      </div>`
    ).join('');
  }

  // 事件委托处理删除（避免全局函数污染）
  function initProductListEvents() {
    $('productList').addEventListener('click', async e => {
      const btn = e.target.closest('.btn-delete-product');
      if (!btn) return;
      const id = parseInt(btn.dataset.id, 10);
      const ok = await confirm('确定要删除该产品吗？此操作不可撤销。');
      if (!ok) return;
      try {
        await ApiClient.del('/api/products/' + id);
        _productCache = _productCache.filter(p => p.id !== id);
        renderProductList();
        Toast.success('产品已删除');
      } catch (e) {
        Toast.error('删除失败：' + e.message);
      }
    });
  }

  function initManageList() {
    const searchInput = $('searchProduct');
    const btnExport   = $('btnExportProducts');
    const btnSort     = $('btnSortEmission');

    const debouncedSearch = debounce(() => loadProductList(searchInput.value.trim()), 300);
    searchInput.addEventListener('input', debouncedSearch);

    btnExport.addEventListener('click', () => {
      if (!_productCache.length) { Toast.info('暂无数据可导出'); return; }
      exportCSV(
        _productCache.map(p => [p.product_name, p.carbon_type, p.carbon_footprint, p.co2_per_unit, p.unit, p.price_per_ton]),
        ['产品名称', '碳种类', '碳足迹描述', 'CO2当量(kg)', '单位', '碳价(元/吨)'],
        'custom_products.csv'
      );
      Toast.success('CSV 已导出');
    });

    btnSort.addEventListener('click', () => {
      if (_sortField === 'co2_per_unit') {
        _sortAsc = !_sortAsc;
      } else {
        _sortField = 'co2_per_unit';
        _sortAsc = false;
      }
      btnSort.textContent = `按排放量排序 ${_sortAsc ? '↑' : '↓'}`;
      renderProductList();
    });
  }

  // ─── 面板4：统计报表 ──────────────────────────────────────
  async function loadStats() {
    const statsGrid    = $('statsGrid');
    const categoryList = $('categoryList');
    statsGrid.innerHTML    = '加载中...';
    categoryList.innerHTML = '加载中...';

    try {
      const [statsBody, catBody] = await Promise.all([
        ApiClient.get('/api/invoice/stats'),
        ApiClient.get('/api/invoice/categories'),
      ]);
      const stats      = unwrap(statsBody);
      const categories = unwrap(catBody);

      if (stats && Object.keys(stats).length) {
        let totalCount = 0, totalAmount = 0, totalEmission = 0;
        let cardsHtml = '';
        for (const [scope, s] of Object.entries(stats)) {
          totalCount    += s.count;
          totalAmount   += s.total_amount;
          totalEmission += s.total_emission_kg;
          const sc = scope.includes('1') ? 'scope1' : scope.includes('2') ? 'scope2' : 'scope3';
          cardsHtml += `<div class="stat-card">
            <div class="label"><span class="scope-tag ${sc}">${scope}</span></div>
            <div class="value">${s.count} 条</div>
            <div style="color:var(--muted);font-size:0.8rem;">¥${s.total_amount} | ${s.total_emission_kg} kg</div>
          </div>`;
        }
        statsGrid.innerHTML = `<div class="stat-card">
          <div class="label">合计</div>
          <div class="value">${totalCount} 条</div>
          <div style="color:var(--muted);font-size:0.8rem;">¥${totalAmount.toFixed(2)} | ${totalEmission.toFixed(4)} kg</div>
        </div>` + cardsHtml;
      } else {
        statsGrid.innerHTML = '<p style="color:var(--muted)">暂无统计数据，请先上传发票</p>';
      }

      if (categories && categories.length) {
        function scopeClass(scope) {
          if (!scope) return '';
          if (scope.includes('1')) return 'scope1';
          if (scope.includes('2')) return 'scope2';
          return 'scope3';
        }
        let tbl = '<table class="category-table"><tr><th>发票号</th><th>名称</th><th>范围</th><th>匹配</th><th>金额</th><th>排放(kg)</th><th>时间</th></tr>';
        for (const c of categories) {
          tbl += `<tr><td>${c.invoice_number || '-'}</td><td>${(c.line_name || '').replace(/\s+/g, ' ').trim()}</td>
            <td><span class="scope-tag ${scopeClass(c.scope)}">${c.scope}</span></td>
            <td>${c.match_type}</td><td>¥${c.amount}</td><td>${c.emission_kg}</td><td>${c.created_at || '-'}</td></tr>`;
        }
        tbl += '</table>';
        tbl += `<button class="secondary" id="btnExportStats" style="margin-top:0.75rem;">导出 CSV</button>`;
        categoryList.innerHTML = tbl;

        $('btnExportStats').addEventListener('click', () => {
          exportCSV(
            categories.map(c => [c.invoice_number, (c.line_name || '').replace(/\s+/g, ' ').trim(), c.scope, c.match_type, c.amount, c.emission_kg, c.created_at]),
            ['发票号', '名称', '范围', '匹配方式', '金额', '排放(kg)', '时间'],
            'invoice_categories.csv'
          );
          Toast.success('CSV 已导出');
        });
      } else {
        categoryList.innerHTML = '<p style="color:var(--muted)">暂无类别记录</p>';
      }
    } catch (e) {
      statsGrid.innerHTML    = '加载失败';
      categoryList.innerHTML = '';
      Toast.error('统计加载失败：' + e.message);
    }
  }

  // ─── 初始化 ───────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    initTabs();
    initQueryPanel();
    initInvoicePanel();
    initManagePanel();
    initManageList();
    initProductListEvents();
    loadProductList();
  });

})();
