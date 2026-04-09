type DiffMark = 'same' | 'added' | 'removed' | 'empty';
type DiffRow = { left: string; right: string; leftMark: DiffMark; rightMark: DiffMark };

function buildGreedyDiff(currentText: string, baselineText: string): DiffRow[] {
  const current = (currentText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const baseline = (baselineText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < baseline.length || j < current.length) {
    const left = baseline[i];
    const right = current[j];
    if (left !== undefined && right !== undefined && left === right) {
      rows.push({ left, right, leftMark: 'same', rightMark: 'same' });
      i += 1;
      j += 1;
      continue;
    }
    if (right !== undefined && baseline[i] !== undefined && current[j + 1] === baseline[i]) {
      rows.push({ left: '', right, leftMark: 'empty', rightMark: 'added' });
      j += 1;
      continue;
    }
    if (left !== undefined && current[j] !== undefined && baseline[i + 1] === current[j]) {
      rows.push({ left, right: '', leftMark: 'removed', rightMark: 'empty' });
      i += 1;
      continue;
    }
    rows.push({
      left: left || '',
      right: right || '',
      leftMark: left ? 'removed' : 'empty',
      rightMark: right ? 'added' : 'empty',
    });
    i += left ? 1 : 0;
    j += right ? 1 : 0;
  }
  return rows.slice(0, 220);
}

function buildSideBySideDiff(currentText: string, baselineText: string): DiffRow[] {
  const current = (currentText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const baseline = (baselineText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  if (baseline.length * current.length > 45000) {
    return buildGreedyDiff(currentText, baselineText);
  }

  const n = baseline.length;
  const m = current.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array<number>(m + 1).fill(0));

  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (baseline[i] === current[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (baseline[i] === current[j]) {
      rows.push({ left: baseline[i], right: current[j], leftMark: 'same', rightMark: 'same' });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ left: baseline[i], right: '', leftMark: 'removed', rightMark: 'empty' });
      i += 1;
    } else {
      rows.push({ left: '', right: current[j], leftMark: 'empty', rightMark: 'added' });
      j += 1;
    }
  }
  while (i < n) {
    rows.push({ left: baseline[i], right: '', leftMark: 'removed', rightMark: 'empty' });
    i += 1;
  }
  while (j < m) {
    rows.push({ left: '', right: current[j], leftMark: 'empty', rightMark: 'added' });
    j += 1;
  }
  return rows.slice(0, 260);
}

self.onmessage = (event: MessageEvent<{ currentText: string; baselineText: string }>) => {
  const { currentText, baselineText } = event.data;
  const rows = buildSideBySideDiff(currentText, baselineText);
  self.postMessage(rows);
};
