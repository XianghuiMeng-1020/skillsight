const fs = require('fs');
const path = require('path');

const outDir = path.join(__dirname, '..', 'out');

function copyIfExists(sourceRelative, targetRelative) {
  const source = path.join(outDir, sourceRelative);
  const target = path.join(outDir, targetRelative);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing source file: ${source}`);
  }
  fs.copyFileSync(source, target);
}

copyIfExists(path.join('documents', '_.html'), 'document-view.html');
