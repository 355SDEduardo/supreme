/**
 * Supreme — Plataforma Contábil Unificada
 * Native Canvas 2D Charting Engine (Zero External Dependencies)
 * Paleta executiva clara Supreme (--accent: #166659, --ink: #172b42, --border: #cbd5e1)
 */

const MiniCharts = {
  /**
   * Draws a smooth Cash Flow projection line/area chart with zero-line indicator.
   */
  drawCashFlowLineChart(canvasId, series = []) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = (rect.width || 600) * dpr;
    canvas.height = (rect.height || 260) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 600;
    const height = rect.height || 260;
    ctx.clearRect(0, 0, width, height);

    if (!series || series.length === 0) {
      this._drawEmptyState(ctx, width, height, 'Sem projeção de fluxo de caixa disponível');
      return;
    }

    const padLeft = 68;
    const padRight = 24;
    const padTop = 24;
    const padBottom = 36;
    const chartW = width - padLeft - padRight;
    const chartH = height - padTop - padBottom;

    const values = series.map(d => Number(d.projected_balance || 0));
    const minVal = Math.min(0, ...values);
    const maxVal = Math.max(1000, ...values);
    const range = (maxVal - minVal) || 1;

    // Horizontal grid lines (Supreme light theme)
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1;
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const y = padTop + (chartH / steps) * i;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();

      const labelVal = maxVal - (range / steps) * i;
      ctx.fillStyle = '#52657a';
      ctx.font = '11px Inter, system-ui, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(this._compactCurrency(labelVal), padLeft - 8, y + 4);
    }

    // Zero line if minVal < 0
    if (minVal < 0) {
      const zeroY = padTop + ((maxVal - 0) / range) * chartH;
      ctx.strokeStyle = 'rgba(185, 28, 28, 0.45)';
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(padLeft, zeroY);
      ctx.lineTo(width - padRight, zeroY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    const points = series.map((d, idx) => {
      const x = padLeft + (idx / Math.max(1, series.length - 1)) * chartW;
      const y = padTop + ((maxVal - Number(d.projected_balance)) / range) * chartH;
      return { x, y, raw: d };
    });

    // Area fill with Supreme emerald gradient
    const grad = ctx.createLinearGradient(0, padTop, 0, padTop + chartH);
    grad.addColorStop(0, 'rgba(22, 102, 89, 0.24)');
    grad.addColorStop(1, 'rgba(22, 102, 89, 0.01)');

    ctx.beginPath();
    ctx.moveTo(points[0].x, padTop + chartH);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, padTop + chartH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Main line
    ctx.beginPath();
    points.forEach((p, idx) => {
      if (idx === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.strokeStyle = '#166659';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Points & X-axis labels
    const labelStep = Math.max(1, Math.floor(points.length / 6));
    points.forEach((p, idx) => {
      const isNegative = Number(p.raw.projected_balance) < 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, isNegative ? 4.5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = isNegative ? '#b91c1c' : '#0f4c42';
      ctx.fill();

      if (idx % labelStep === 0 || idx === points.length - 1) {
        ctx.fillStyle = '#52657a';
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.textAlign = 'center';
        const shortDate = String(p.raw.date || '').slice(5);
        ctx.fillText(shortDate, p.x, height - 10);
      }
    });
  },

  /**
   * Draws a Donut Chart for DRE Expense/Revenue Composition or Tax Regime Breakdown.
   */
  drawDonutChart(canvasId, segments = [], centerLabel = '') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = (rect.width || 360) * dpr;
    canvas.height = (rect.height || 230) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 360;
    const height = rect.height || 230;
    ctx.clearRect(0, 0, width, height);

    const total = segments.reduce((acc, s) => acc + Math.max(0, Number(s.value || 0)), 0);
    if (total <= 0) {
      this._drawEmptyState(ctx, width, height, 'Sem dados para o gráfico');
      return;
    }

    const cx = Math.min(width * 0.34, height * 0.5);
    const cy = height * 0.5;
    const radius = Math.min(cx, cy) - 18;
    const innerRadius = radius * 0.62;

    let startAngle = -Math.PI / 2;
    segments.forEach(seg => {
      const val = Math.max(0, Number(seg.value || 0));
      const sliceAngle = (val / total) * (Math.PI * 2);
      ctx.beginPath();
      ctx.arc(cx, cy, radius, startAngle, startAngle + sliceAngle);
      ctx.arc(cx, cy, innerRadius, startAngle + sliceAngle, startAngle, true);
      ctx.closePath();
      ctx.fillStyle = seg.color || '#166659';
      ctx.fill();
      startAngle += sliceAngle;
    });

    // Center text
    ctx.fillStyle = '#172b42';
    ctx.font = 'bold 13px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(centerLabel || this._compactCurrency(total), cx, cy + 4);

    // Legend on the right
    const legendX = cx + radius + 24;
    let legendY = cy - (segments.length * 14);
    segments.forEach(seg => {
      const pct = ((Math.max(0, Number(seg.value || 0)) / total) * 100).toFixed(1);
      ctx.fillStyle = seg.color || '#166659';
      ctx.fillRect(legendX, legendY - 8, 10, 10);

      ctx.fillStyle = '#172b42';
      ctx.font = '11px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`${seg.label}: ${pct}%`, legendX + 16, legendY + 1);
      legendY += 24;
    });
  },

  /**
   * Draws Horizontal Progress Bars (e.g. Analyst Workload or Aging Brackets).
   */
  drawHorizontalBars(containerId, items = []) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!items || items.length === 0) {
      container.innerHTML = '<div class="empty-state">Sem registros para exibir.</div>';
      return;
    }

    const maxVal = Math.max(1, ...items.map(i => Number(i.value || 0)));
    container.innerHTML = items.map(item => {
      const pct = Math.min(100, Math.round((Number(item.value || 0) / maxVal) * 100));
      const color = item.color || 'var(--accent)';
      return `
        <div style="margin-bottom: 12px;">
          <div style="display:flex; justify-content:space-between; font-size:0.82rem; margin-bottom:5px;">
            <span style="color:var(--ink); font-weight:600;">${item.label}</span>
            <span class="mono" style="color:var(--muted); font-weight:600;">${item.formattedValue || item.value}</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" style="width:${pct}%; background:${color};"></div>
          </div>
        </div>
      `;
    }).join('');
  },

  _drawEmptyState(ctx, width, height, text) {
    ctx.fillStyle = '#52657a';
    ctx.font = '12px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(text, width / 2, height / 2);
  },

  _compactCurrency(val) {
    const num = Number(val || 0);
    if (Math.abs(num) >= 1_000_000) return `R$ ${(num / 1_000_000).toFixed(1)}M`;
    if (Math.abs(num) >= 1_000) return `R$ ${(num / 1_000).toFixed(1)}k`;
    return `R$ ${num.toFixed(0)}`;
  }
};

window.MiniCharts = MiniCharts;
