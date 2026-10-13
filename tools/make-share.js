/* 生成"单文件分享版"：把所有用到的素材以 data URL 内嵌，发一个文件就能玩 */
const fs = require('fs');
const path = require('path');
const dir = __dirname;
const src = fs.readFileSync(path.join(dir, 'breeze-giant-city.html'), 'utf8');

const needed = ['assets/breeze-front.png', 'assets/breeze-side.png', 'assets/breeze-back.png', 'assets/ending.png'];
for (const v of ['front', 'side', 'back']) for (let i = 0; i < 8; i++) needed.push('assets/walk-' + v + '-' + i + '.png');

let out = src;
let total = 0;
// 走路帧是动态拼路径加载的：这里内嵌成一张查找表，并改写加载处
const walkData = {};
for (const v of ['front', 'side', 'back']) for (let i = 0; i < 8; i++) {
  const rel = 'assets/walk-' + v + '-' + i + '.png';
  const b64 = fs.readFileSync(path.join(dir, rel)).toString('base64');
  total += b64.length;
  walkData[v + '-' + i] = 'data:image/png;base64,' + b64;
}
const loaderOld = "      im.src = 'assets/walk-' + v + '-' + i + '.png';";
const loaderNew = "      im.src = (typeof WALK_FRAME_DATA !== 'undefined' && WALK_FRAME_DATA[v + '-' + i]) || ('assets/walk-' + v + '-' + i + '.png');";
if (!out.includes(loaderOld)) { console.error('找不到走路帧加载处'); process.exit(1); }
out = out.replace(loaderOld, loaderNew);

// 静态引用的素材（三视图 + 终章立绘）直接替换成 data URL
for (const rel of ['assets/breeze-front.png', 'assets/breeze-side.png', 'assets/breeze-back.png', 'assets/ending.png']) {
  const b64 = fs.readFileSync(path.join(dir, rel)).toString('base64');
  total += b64.length;
  if (!out.includes(rel)) { console.error('HTML 未引用 ' + rel); process.exit(1); }
  out = out.split(rel).join('data:image/png;base64,' + b64);
}
// 注入查找表
const head = '"use strict";';
out = out.replace(head, head + '\nconst WALK_FRAME_DATA = ' + JSON.stringify(walkData) + ';\n');
// 外部音效在单文件版里不再适用（保留合成音）
out = out.replace(
  "<p class=\"tip\">单文件 Canvas 游戏 · 无需联网 · 可选：把 step.mp3 / collapse.mp3 放进 assets/sfx/ 即可用你自己的音效</p>",
  "<p class=\"tip\">单文件分享版 · 所有素材已内嵌，双击即可玩 · 无需联网 · 手机打开会有虚拟摇杆与按键</p>"
);
out = out.replace("const SAMPLES = { step: 'assets/sfx/step.mp3', collapse: 'assets/sfx/collapse.mp3', eat: 'assets/sfx/eat.mp3', steal: 'assets/sfx/steal.mp3' };",
  "const SAMPLES = {};   // 分享版使用内置合成音效");

const dst = path.join(dir, '布瑞泽-巨兽之城-分享版.html');
fs.writeFileSync(dst, out, 'utf8');
console.log('已生成 ' + path.basename(dst) + '：' + (out.length / 1024 / 1024).toFixed(2) + ' MB（内嵌素材 ' + (total / 1024 / 1024).toFixed(2) + ' MB base64）');
