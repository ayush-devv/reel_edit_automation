import os from "node:os";
const cpus = os.cpus();
console.log(JSON.stringify({ model: cpus[0]?.model, cores: cpus.length, memGB: Math.round(os.totalmem() / 2 ** 30), arch: os.arch() }));
