// Persona Relay sidecar (sandbox). The Python app calls this on 127.0.0.1:8790.
//   POST /start  {claimType, reference}  -> {id, url}            (creates a Relay session + Privacy Pass)
//   POST /claim  {id}                    -> {claim_result, ...}  (redeems the claim; one use)
// Secrets (relay secret, privacy pass) never leave this process.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import personaPkg from "@persona/sdk-node";
const { Persona } = personaPkg;

const here = path.dirname(fileURLToPath(import.meta.url));
const env = Object.fromEntries(
  fs.readFileSync(path.join(here, "..", ".env"), "utf8").split(/\r?\n/)
    .filter((l) => /^[A-Z_]+=/.test(l)).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()]));
const apiKey = process.env.PERSONA_RELAY_KEY || env.PERSONA_RELAY_KEY || env.PERSONA_API_KEY;
if (!apiKey) { console.error("PERSONA_RELAY_KEY missing"); process.exit(1); }
const persona = new Persona({ apiKey });
const sessions = new Map();

const send = (res, code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };

http.createServer(async (req, res) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  const body = raw ? JSON.parse(raw) : {};
  try {
    if (req.method === "GET" && req.url === "/health") return send(res, 200, { ok: true });
    if (req.method === "POST" && req.url === "/start") {
      const claimType = body.claimType || "age_over21_verified";
      const { relayToken, relaySecret, relaySessionAccessToken } = await persona.relays.create({ claimType, encryptionKeyJwk: null });
      const { privacyPassToken } = await persona.relays.issuePrivacyPass({ claimType });
      const id = crypto.randomUUID();
      sessions.set(id, { claimType, relayToken, relaySecret, privacyPassToken, reference: body.reference });
      const url = `https://relay.withpersona.com/relay?relay-session-access-token=${encodeURIComponent(relaySessionAccessToken)}&theme=light`;
      return send(res, 200, { id, claim_type: claimType, url });
    }
    if (req.method === "POST" && req.url === "/claim") {
      const s = sessions.get(body.id);
      if (!s) return send(res, 404, { error: "unknown relay session" });
      const { claimPayload, tokenConsumed } = await persona.relays.generateClaim({
        relayToken: s.relayToken, relaySecret: s.relaySecret, privacyPassToken: s.privacyPassToken });
      const claim = JSON.parse(claimPayload);
      sessions.delete(body.id);
      return send(res, 200, { claim_type: claim.claim_type, claim_result: claim.claim_result, methodology: claim.methodology ?? null,
        token_consumed: tokenConsumed, reference: s.reference, sandbox: apiKey.startsWith("persona_sandbox") });
    }
    send(res, 404, { error: "not found" });
  } catch (e) {
    send(res, 502, { error: e?.title || e?.message || String(e), code: e?.code ?? null, status: e?.statusCode ?? null });
  }
}).listen(8790, "127.0.0.1", () => console.log("relay sidecar on 127.0.0.1:8790"));
