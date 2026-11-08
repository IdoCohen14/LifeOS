type Env = Record<string, string | undefined>;

function port(value: string) {
  if (!/^[0-9]+$/.test(value) || Number(value) < 1024 || Number(value) > 65535)
    throw new Error("Invalid loopback service port");
  return Number(value);
}

export function deploymentConfig(env: Env = process.env) {
  const mode = env.LIFEOS_DEPLOYMENT_MODE || "local";
  if (mode !== "local" && mode !== "server") throw new Error("Unknown deployment mode");
  const webPort = port(env.LIFEOS_WEB_PORT || "3000");
  const apiPort = port(env.LIFEOS_API_PORT || "8765");
  if (webPort === apiPort) throw new Error("Service ports must differ");
  const value = env.LIFEOS_PUBLIC_ORIGIN || "";
  let origin = `http://127.0.0.1:${webPort}`;
  if (mode === "server") {
    if (!value || /[^\x21-\x7e]|[\\?#]/.test(value)) throw new Error("Invalid HTTPS public origin");
    const url = new URL(value);
    const host = url.hostname;
    if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" ||
        host.length > 253 || !host.includes(".") || /\.(local|localhost|internal)$/.test(host) ||
        /^[0-9.]+$/.test(host) ||
        host.split(".").some(label => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label)) ||
        !/^(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$/.test(host.split(".").at(-1) || "") ||
        (url.port !== "" && (Number(url.port) < 1 || Number(url.port) > 65535)))
      throw new Error("Invalid HTTPS public origin");
    origin = url.origin;
  } else if (value) throw new Error("Public origin requires explicit server mode");
  return { server: mode === "server", origin, webPort, apiPort,
    accountMode: mode === "server" || env.LIFEOS_ACCOUNT_MODE === "1" };
}
