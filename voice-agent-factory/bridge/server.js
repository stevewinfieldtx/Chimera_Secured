/**
 * Voice Agent Bridge - Shared Knowledge Retrieval Service
 *
 * Sits between ALL ElevenLabs voice agents and the Orchestrator.
 * Product-agnostic: the collection_id in each request determines
 * which TDE collection gets queried.
 *
 * Reads env from ../.env (single file at factory root).
 */

var fs = require("fs");
var pathMod = require("path");

// Load ../.env
var envPath = pathMod.join(__dirname, "..", ".env");
if (fs.existsSync(envPath)) {
  fs.readFileSync(envPath, "utf8").split("\n").forEach(function(line) {
    var t = line.trim();
    if (!t || t.startsWith("#")) return;
    var eq = t.indexOf("=");
    if (eq > 0) {
      var k = t.slice(0, eq).trim();
      var v = t.slice(eq + 1).trim();
      if (!process.env[k]) process.env[k] = v;
    }
  });
}

var express = require("express");
var app = express();
app.use(express.json());

var ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || "http://localhost:8500";
var BRIDGE_PORT = parseInt(process.env.BRIDGE_PORT || "3100", 10);
var BRIDGE_SECRET = process.env.BRIDGE_SECRET || "";

function verifySecret(req, res, next) {
  if (!BRIDGE_SECRET) return next();
  if ((req.headers["x-webhook-secret"] || "") !== BRIDGE_SECRET) {
    console.warn("[bridge] Rejected - bad secret from " + req.ip);
    return res.status(401).json({ error: "unauthorized" });
  }
  next();
}

app.get("/health", function(_req, res) {
  res.json({ service: "voice-agent-bridge", version: "1.0.0", orchestrator: ORCHESTRATOR_URL });
});

app.post("/get-knowledge", verifySecret, async function(req, res) {
  var start = Date.now();
  var query = req.body.query || req.body.question || req.body.text || "";
  var collectionId = req.body.collection_id || process.env.DEFAULT_COLLECTION_ID || "general";

  if (!query.trim()) {
    return res.json({ answer: "I didn't quite catch the question. Could you rephrase that?" });
  }

  console.log("[bridge] [" + collectionId + "] " + query);

  try {
    var payload = {
      collection_id: collectionId,
      query: query,
      conversation_history: [],
      persona: req.body.persona || "partner_msp",
      response_style: "conversational"
    };

    var orchRes = await fetch(ORCHESTRATOR_URL + "/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10000)
    });

    if (!orchRes.ok) {
      var err = await orchRes.text();
      console.error("[bridge] Orchestrator " + orchRes.status + ": " + err);
      return res.json({
        answer: "I'm having trouble pulling up that information right now. Can I have someone follow up with you?"
      });
    }

    var data = await orchRes.json();
    var answer = data.response || data.answer || data.text || "";
    console.log("[bridge] [" + collectionId + "] " + (Date.now() - start) + "ms");
    return res.json({ answer: answer });
  } catch (e) {
    console.error("[bridge] Error: " + e.message);
    return res.json({
      answer: "I'm having a little trouble with that. Could you ask another way, or I can have someone follow up?"
    });
  }
});

app.listen(BRIDGE_PORT, function() {
  console.log("[bridge] Running on port " + BRIDGE_PORT);
  console.log("[bridge] Orchestrator: " + ORCHESTRATOR_URL);
  console.log("[bridge] Secret: " + (BRIDGE_SECRET ? "on" : "off"));
});
