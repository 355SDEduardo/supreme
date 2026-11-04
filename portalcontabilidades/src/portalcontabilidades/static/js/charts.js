/**
 * High-performance HTML5 Canvas Charts for Portal Contabilidades & BPO
 * Zero-dependency, retina-ready, smooth gradients and hover interactions.
 */

class MiniCharts {
  static setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return { ctx, width: rect.width, height: rect.height };
  }

  /**
   * Cash Flow Timeline Chart with Negative Balance Deficit Highlight
   */
  static drawCashFlow(canvasId, timeline = []) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !timeline.length) return;

    const { ctx, width, height } = this.setupCanvas(canvas);
    const padding = { top: 30, right: 30, bottom: 40, left: 70 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const balances = timeline.map(t => Number(t.closing_balance || 0));
    const minVal = Math.min(0, Math.min(...balances));
    const maxVal = Math.max(1000, Math.max(...balances)) * 1.15;
    const range = maxVal - minVal || 1;

    const getX = (i) => padding.left + (i / (timeline.length - 1 || 1)) * chartW;
    const getY = (val) => padding.top + chartH - ((val - minVal) / range) * chartH;
    const zeroY = getY(0);

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Draw Grid Lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    const gridSteps = 4;
    for (let i = 0; i <= gridSteps; i++) {
      const v = minVal + (range / gridSteps) * i;
      const y = getY(v);
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      // Label
      ctx.fillStyle = '#6b7280';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`R$ ${(v / 1000).toFixed(0)}k`, padding.left - 10, y + 3);
    }

    // Zero Line
    if (zeroY >= padding.top && zeroY <= padding.top + chartH) {
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(padding.left, zeroY);
      ctx.lineTo(width - padding.right, zeroY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Area Gradient
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
    gradient.addColorStop(0.7, 'rgba(59, 130, 246, 0.05)');
    gradient.addColorStop(1, 'rgba(239, 68, 68, 0.25)');

    ctx.beginPath();
    ctx.moveTo(getX(0), zeroY);
    timeline.forEach((item, i) => {
      ctx.lineTo(getX(i), getY(Number(item.closing_balance)));
    });
    ctx.lineTo(getX(timeline.length - 1), zeroY);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line Path
    ctx.beginPath();
    timeline.forEach((item, i) => {
      const x = getX(i);
      const y = getY(Number(item.closing_balance));
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Data points & highlight negatives
    timeline.forEach((item, i) => {
      const x = getX(i);
      const val = Number(item.closing_balance);
      const y = getY(val);
      const isNeg = val < 0;

      ctx.beginPath();
      ctx.arc(x, y, isNeg ? 5 : 3.5, 0, Math.PI * 2);
      ctx.fillStyle = isNeg ? '#ef4444' : '#60a5fa';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    // Date X Labels (sampled)
    ctx.fillStyle = '#9ca3af';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'center';
    const step = Math.max(1, Math.floor(timeline.length / 6));
    for (let i = 0; i < timeline.length; i += step) {
      const d = timeline[i].date ? timeline[i].date.substring(5) : `D${i+1}`;
      ctx.fillText(d, getX(i), height - 15);
    }
  }

  /**
   * Donut Chart with Center Summary Label
   */
  static drawDonut(canvasId, items = [], centerText = '') {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !items.length) return;

    const { ctx, width, height } = this.setupCanvas(canvas);
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(centerX, centerY) - 15;
    const innerRadius = radius * 0.65;

    const total = items.reduce((acc, it) => acc + (it.value || 0), 0);
    if (total === 0) return;

    let startAngle = -Math.PI / 2;
    ctx.clearRect(0, 0, width, height);

    items.forEach((it) => {
      const sliceAngle = ((it.value || 0) / total) * Math.PI * 2;
      const endAngle = startAngle + sliceAngle;

      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, startAngle, endAngle);
      ctx.arc(centerX, centerY, innerRadius, endAngle, startAngle, true);
      ctx.closePath();

      ctx.fillStyle = it.color || '#3b82f6';
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#0f1523';
      ctx.stroke();

      startAngle = endAngle;
    });

    // Center text
    if (centerText) {
      ctx.fillStyle = '#fff';
      ctx.font = '700 18px Outfit, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(centerText, centerX, centerY);
    }
  }

  /**
   * Horizontal Bar Chart (e.g. DRE breakdown or Workload)
   */
  static drawBarChart(canvasId, categories = []) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !categories.length) return;

    const { ctx, width, height } = this.setupCanvas(canvas);
    ctx.clearRect(0, 0, width, height);

    const padding = { top: 15, right: 30, bottom: 25, left: 140 };
    const chartW = width - padding.left - padding.right;
    const barHeight = Math.min(24, (height - padding.top - padding.bottom) / categories.length - 10);
    const maxVal = Math.max(...categories.map(c => Math.abs(c.value || 0))) || 1;

    categories.forEach((cat, i) => {
      const y = padding.top + i * (barHeight + 12);
      const barW = (Math.abs(cat.value || 0) / maxVal) * chartW;

      // Label
      ctx.fillStyle = '#9ca3af';
      ctx.font = '12px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(cat.label, padding.left - 10, y + barHeight / 2);

      // Bar
      ctx.fillStyle = cat.color || '#3b82f6';
      ctx.beginPath();
      ctx.roundRect(padding.left, y, Math.max(4, barW), barHeight, 4);
      ctx.fill();

      // Value text
      ctx.fillStyle = '#fff';
      ctx.font = '600 11px Inter, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(cat.displayValue || cat.value, padding.left + barW + 8, y + barHeight / 2);
    });
  }
}

window.MiniCharts = MiniCharts;
