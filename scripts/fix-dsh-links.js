// 把 integrations/dsh/node_modules 下的每个包，链接到 dsh-home/profiles/node_modules
// 理由：dsh 从 runtime/dsh-home/profiles/web/ 加载插件，Node 往上找 node_modules 时
// 到不了 integrations/dsh/node_modules，必须靠这一层 fallback 链接。
// Bash 上下文有权限建 junction；计划任务上下文没有（EPERM），所以提前建好。
const fs = require("fs");
const path = require("path");

const SRC = "D:\\AI\\ninfer-local\\integrations\\dsh\\node_modules";
const DST = "D:\\AI\\ninfer-local\\runtime\\dsh-home\\profiles\\node_modules";

let made = 0, kept = 0, failed = 0;

function linkOne(srcDir, dstPath) {
  try {
    const st = fs.lstatSync(dstPath);
    if (st.isSymbolicLink()) { kept++; return; }
    if (st.isDirectory()) { kept++; return; }
    fs.rmSync(dstPath, { force: true });
  } catch { /* 不存在，继续建 */ }

  try {
    fs.mkdirSync(path.dirname(dstPath), { recursive: true });
    fs.symlinkSync(srcDir, dstPath, "junction");
    made++;
  } catch (e) {
    failed++;
    if (failed <= 3) console.log("  失败:", path.basename(dstPath), e.code);
  }
}

fs.mkdirSync(DST, { recursive: true });

for (const name of fs.readdirSync(SRC)) {
  if (name.startsWith(".")) continue;
  const s = path.join(SRC, name);
  if (!fs.statSync(s).isDirectory()) continue;

  if (name.startsWith("@")) {
    fs.mkdirSync(path.join(DST, name), { recursive: true });
    for (const sub of fs.readdirSync(s)) {
      const ss = path.join(s, sub);
      if (!fs.statSync(ss).isDirectory()) continue;
      linkOne(ss, path.join(DST, name, sub));
    }
  } else {
    linkOne(s, path.join(DST, name));
  }
}

console.log(`建立 ${made} 个，已存在 ${kept} 个，失败 ${failed} 个`);
console.log("总数:", fs.readdirSync(DST).length);
