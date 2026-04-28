#!/usr/bin/env node
var fs = require("fs");
var path = require("path");

// Load .env
var envPath = path.join(__dirname, ".env");
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

var ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY;
var TWILIO_ACCOUNT_SID = process.env.TWILIO_ACCOUNT_SID;
var TWILIO_AUTH_TOKEN = process.env.TWILIO_AUTH_TOKEN;
var EL_BASE = "https://api.elevenlabs.io/v1";

function fatal(msg) { console.error("\n  ERROR: " + msg + "\n"); process.exit(1); }

function parseArgs() {
  var args = process.argv.slice(2);
  var o = {};
  for (var i = 0; i < args.length; i++) {
    if (args[i] === "--config" && args[i+1]) o.configPath = args[++i];
    else if (args[i] === "--dry-run") o.dryRun = true;
    else if (args[i] === "--list") o.listApps = true;
    else if (args[i] === "--voices") o.showVoices = true;
    else if (args[i] === "--voice-assignments") o.showAssignments = true;
    else if (args[i] === "--gender" && args[i+1]) o.voiceGender = args[++i].toLowerCase();
    else if (args[i] === "--category" && args[i+1]) o.voiceCategory = args[++i].toLowerCase();
    else if (args[i] === "--help" || args[i] === "-h") {
      console.log([
        "",
        "  Voice Agent Factory",
        "",
        "  Usage:",
        "    node agent-factory.js --config <file> [--dry-run]",
        "    node agent-factory.js --list",
        "    node agent-factory.js --voices [--gender male|female] [--category premade|cloned]",
        "    node agent-factory.js --voice-assignments",
        "",
      ].join("\n"));
      process.exit(0);
    }
  }
  return o;
}

function loadTemplate(name) {
  var tp = path.join(__dirname, "templates", name + ".md");
  if (!fs.existsSync(tp)) fatal("Template not found: " + tp);
  return fs.readFileSync(tp, "utf8");
}

function fillTemplate(template, vars) {
  var result = template;
  Object.keys(vars).forEach(function(k) {
    var re = new RegExp("\\{" + k + "\\}", "g");
    result = result.replace(re, vars[k]);
  });
  return result;
}

function buildPromptVars(raw) {
  var vars = {};
  if (raw.prompt_vars) {
    Object.keys(raw.prompt_vars).forEach(function(k) { vars[k] = raw.prompt_vars[k]; });
  }
  if (raw.partner && !vars.partner_context) {
    vars.partner_context = ", embedded on " + (vars.partner_name || raw.partner) + "\'s website. You help " + (vars.partner_name || raw.partner) + "\'s customers and sales team understand the product";
  }
  if (!vars.partner_context) vars.partner_context = "";
  if (raw.partner && !vars.partner_guardrails) {
    vars.partner_guardrails = "- Never make claims about " + (vars.partner_name || raw.partner) + "\'s pricing, SLAs, or service terms. Those are theirs to discuss.";
  }
  if (!vars.partner_guardrails) vars.partner_guardrails = "";
  return vars;
}

function loadConfig(cfgPath) {
  var resolved = path.resolve(cfgPath);
  if (!fs.existsSync(resolved)) fatal("Config not found: " + resolved);
  var raw = JSON.parse(fs.readFileSync(resolved, "utf8"));
  if (raw.prompt_template) {
    var tmpl = loadTemplate(raw.prompt_template);
    var vars = buildPromptVars(raw);
    raw.system_prompt = fillTemplate(tmpl, vars);
  } else if (raw.system_prompt_file) {
    var pp = path.resolve(path.dirname(resolved), raw.system_prompt_file);
    if (!fs.existsSync(pp)) fatal("System prompt not found: " + pp);
    raw.system_prompt = fs.readFileSync(pp, "utf8");
  }
  ["agent_name","system_prompt","first_message","voice_id","bridge_url"].forEach(function(f) {
    if (!raw[f]) fatal("Config missing: " + f);
  });
  return raw;
}

// ---- Voice management -------------------------------------------------------

function scanAgentDir(agDir, product, prefix) {
  var configs = [];
  if (!fs.existsSync(agDir)) return configs;
  fs.readdirSync(agDir)
    .filter(function(f) { return f.endsWith(".json") && !f.startsWith("_") && !f.endsWith(".result.json"); })
    .forEach(function(file) {
      try {
        var r = JSON.parse(fs.readFileSync(path.join(agDir, file), "utf8"));
        if (r.voice_id) configs.push({
          voice_id: r.voice_id, product: r.product || product,
          role: r.role || file.replace(".json",""),
          partner: r.partner || null,
          agent_name: r.agent_name || "unknown",
          file: prefix + "/agents/" + file,
          widget_embed: r.widget_embed || false
        });
      } catch(e) {}
    });
  return configs;
}

function getAllAgentConfigs() {
  var appsDir = path.join(__dirname, "applications");
  if (!fs.existsSync(appsDir)) return [];
  var configs = [];
  fs.readdirSync(appsDir, { withFileTypes: true })
    .filter(function(d) { return d.isDirectory() && !d.name.startsWith("_"); })
    .forEach(function(app) {
      configs = configs.concat(scanAgentDir(
        path.join(appsDir, app.name, "agents"), app.name, app.name));
      var partnersDir = path.join(appsDir, app.name, "partners");
      if (fs.existsSync(partnersDir)) {
        fs.readdirSync(partnersDir, { withFileTypes: true })
          .filter(function(d) { return d.isDirectory() && !d.name.startsWith("_"); })
          .forEach(function(partner) {
            configs = configs.concat(scanAgentDir(
              path.join(partnersDir, partner.name, "agents"),
              app.name,
              app.name + "/partners/" + partner.name));
          });
      }
    });
  return configs;
}

function getUsedVoiceIds() {
  var map = {};
  getAllAgentConfigs().forEach(function(c) {
    var label = c.partner ? c.product + "/partner:" + c.partner : c.product + "/" + c.role;
    map[c.voice_id] = label;
  });
  return map;
}

async function browseVoices(gender, category) {
  if (!ELEVENLABS_API_KEY) fatal("ELEVENLABS_API_KEY not set");
  var res = await fetch(EL_BASE + "/voices", { headers: { "xi-api-key": ELEVENLABS_API_KEY } });
  if (!res.ok) fatal("Failed to fetch voices: " + res.status);
  var voices = (await res.json()).voices || [];
  if (gender) {
    var g = gender.startsWith("m") ? "male" : "female";
    voices = voices.filter(function(v) { return (v.labels && v.labels.gender || "").toLowerCase() === g; });
  }
  if (category) {
    voices = voices.filter(function(v) { return (v.category || "").toLowerCase() === category; });
  }
  var used = getUsedVoiceIds();
  console.log("\n  Available Voices (" + voices.length + ")\n");
  console.log("  " + pad("Voice ID", 24) + pad("Name", 16) + pad("Gender", 8) + pad("Category", 14) + "Status");
  console.log("  " + repeat("-", 74));
  voices.forEach(function(v) {
    var gn = pad((v.labels && v.labels.gender) || "?", 8);
    var ct = pad(v.category || "?", 14);
    var st = used[v.voice_id] ? ("IN USE -> " + used[v.voice_id]) : "available";
    console.log("  " + pad(v.voice_id, 24) + pad(v.name || "?", 16) + gn + ct + st);
  });
  console.log("\n  Preview: https://elevenlabs.io/voice-library");
  console.log("  Set voice_id in your agent config JSON to use a voice.\n");
}

function showVoiceAssignments() {
  var configs = getAllAgentConfigs();
  var byVoice = {};
  configs.forEach(function(c) {
    if (!byVoice[c.voice_id]) byVoice[c.voice_id] = [];
    byVoice[c.voice_id].push(c);
  });
  console.log("\n  Voice Assignments\n");
  console.log("  " + pad("Voice ID", 26) + "Assigned To");
  console.log("  " + repeat("-", 60));
  var hasDupes = false;
  Object.keys(byVoice).forEach(function(vid) {
    var agents = byVoice[vid];
    var labels = agents.map(function(c) {
      return c.partner ? c.product + "/partner:" + c.partner : c.product + "/" + c.role;
    });
    var dupe = agents.length > 1;
    if (dupe) hasDupes = true;
    console.log("  " + pad(vid, 26) + labels.join(", ") + (dupe ? " !! DUPLICATE" : ""));
  });
  if (hasDupes) {
    console.log("\n  !!  Duplicate voices found. Each agent should have a unique voice.");
    console.log("      Run: node agent-factory.js --voices\n");
  } else if (configs.length > 0) {
    console.log("\n  OK - No duplicates. Every agent has a unique voice.\n");
  } else {
    console.log("\n  (no agent configs found)\n");
  }
}

function enforceUniqueVoice(config, cfgPath) {
  var all = getAllAgentConfigs();
  var thisFile = path.resolve(cfgPath);
  for (var i = 0; i < all.length; i++) {
    var other = all[i];
    var otherFile = path.resolve(path.join(__dirname, "applications", other.file));
    if (otherFile === thisFile) continue;
    if (other.voice_id === config.voice_id) {
      fatal("Voice " + config.voice_id + " is already used by " + other.product + "/" + other.role +
        " (" + other.file + ").\nEach agent must have a unique voice.\nRun: node agent-factory.js --voices");
    }
  }
}

// ---- List apps --------------------------------------------------------------

function printAgentList(agDir, indent) {
  var agents = fs.existsSync(agDir)
    ? fs.readdirSync(agDir).filter(function(f) { return f.endsWith(".json") && !f.startsWith("_") && !f.endsWith(".result.json"); })
    : [];
  if (agents.length === 0) {
    console.log(indent + "(no agents configured yet)");
  } else {
    agents.forEach(function(a) {
      var hasResult = fs.existsSync(path.join(agDir, a.replace(".json", ".result.json")));
      var info = "";
      try {
        var c = JSON.parse(fs.readFileSync(path.join(agDir, a), "utf8"));
        var vid = (c.voice_id || "?");
        var short = vid.length > 16 ? vid.slice(0,12) + "..." : vid;
        info = " [voice: " + short + "]";
        if (c.widget_embed) info += " [widget]";
        if (c.twilio_phone_number) info += " [phone]";
      } catch(e) {}
      console.log(indent + (hasResult ? "[deployed]" : "[ready]   ") + "  " + a + info);
    });
  }
}

function listApplications() {
  var appsDir = path.join(__dirname, "applications");
  if (!fs.existsSync(appsDir)) fatal("No applications/ directory found.");
  var apps = fs.readdirSync(appsDir, { withFileTypes: true })
    .filter(function(d) { return d.isDirectory() && !d.name.startsWith("_"); });
  console.log("\n  Voice Agent Factory - Applications\n");
  apps.forEach(function(app) {
    console.log("  " + app.name + "/");
    printAgentList(path.join(appsDir, app.name, "agents"), "    ");
    var partnersDir = path.join(appsDir, app.name, "partners");
    if (fs.existsSync(partnersDir)) {
      var partners = fs.readdirSync(partnersDir, { withFileTypes: true })
        .filter(function(d) { return d.isDirectory() && !d.name.startsWith("_"); });
      if (partners.length > 0) {
        console.log("    partners/");
        partners.forEach(function(p) {
          console.log("      " + p.name + "/");
          printAgentList(path.join(partnersDir, p.name, "agents"), "        ");
        });
      }
    }
    console.log();
  });
}

// ---- ElevenLabs API ---------------------------------------------------------

async function apiCall(method, endpoint, body) {
  var base = endpoint.startsWith("/voices") ? EL_BASE : EL_BASE + "/convai";
  var url = base + endpoint;
  var opts = {
    method: method,
    headers: { "xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json" }
  };
  if (body) opts.body = JSON.stringify(body);
  var res = await fetch(url, opts);
  var text = await res.text();
  if (!res.ok) {
    console.error("  API " + method + " " + endpoint + " -> " + res.status);
    console.error("  " + text);
    fatal("ElevenLabs API call failed.");
  }
  return text ? JSON.parse(text) : {};
}

async function createAgent(config) {
  var payload = {
    name: config.agent_name,
    conversation_config: {
      agent: {
        prompt: { prompt: config.system_prompt, llm: config.llm || "gpt-4o", temperature: config.temperature || 0.7 },
        first_message: config.first_message,
        language: config.language || "en"
      },
      tts: { voice_id: config.voice_id }
    }
  };
  if (config.max_duration_seconds) payload.conversation_config.agent.max_duration_s = config.max_duration_seconds;
  console.log("  Creating agent: " + config.agent_name);
  console.log("  Voice: " + config.voice_id);
  var r = await apiCall("POST", "/agents/create", payload);
  console.log("  > Agent created: " + r.agent_id);
  return r.agent_id;
}

async function createTool(config) {
  var payload = {
    name: config.tool_name || "get_knowledge",
    description: config.tool_description || "Retrieve product knowledge from the knowledge base.",
    type: "webhook",
    tool_config: {
      method: "POST",
      url: config.bridge_url + "/get-knowledge",
      headers: Object.assign({ "Content-Type": "application/json" },
        config.bridge_secret ? { "x-webhook-secret": config.bridge_secret } : {}),
      request_body_schema: {
        type: "object",
        properties: {
          query: { type: "string", description: "The question to look up." },
          collection_id: { type: "string", description: "The collection.", enum: [config.collection_id] }
        },
        required: ["query"]
      },
      response_schema: {
        type: "object",
        properties: { answer: { type: "string", description: "The answer." } }
      }
    }
  };
  console.log("  Creating tool: " + payload.name);
  var r = await apiCall("POST", "/tools", payload);
  console.log("  > Tool created: " + r.tool_id);
  return r.tool_id;
}

async function attachToolToAgent(agentId, toolId) {
  console.log("  Attaching tool to agent");
  await apiCall("PATCH", "/agents/" + agentId, { workflow: { tools: [{ tool_id: toolId }] } });
  console.log("  > Tool attached");
}

async function importPhoneNumber(config) {
  if (!config.twilio_phone_number) { console.log("  - No phone, skipping"); return null; }
  if (!TWILIO_ACCOUNT_SID || !TWILIO_AUTH_TOKEN) { console.log("  - Twilio creds missing, skipping"); return null; }
  var payload = {
    phone_number: config.twilio_phone_number, provider: "twilio",
    provider_config: { twilio_account_sid: TWILIO_ACCOUNT_SID, twilio_auth_token: TWILIO_AUTH_TOKEN },
    label: config.phone_label || config.agent_name
  };
  console.log("  Importing phone: " + config.twilio_phone_number);
  var r = await apiCall("POST", "/phone-numbers/create", payload);
  console.log("  > Phone imported: " + r.phone_number_id);
  return r.phone_number_id;
}

async function assignPhoneToAgent(phoneId, agentId) {
  if (!phoneId) return;
  console.log("  Assigning phone to agent");
  await apiCall("PATCH", "/phone-numbers/" + phoneId, { agent_id: agentId });
  console.log("  > Phone assigned");
}

// ---- Helpers ----------------------------------------------------------------

function pad(s, n) { s = String(s); while (s.length < n) s += " "; return s; }
function repeat(ch, n) { var s = ""; for (var i = 0; i < n; i++) s += ch; return s; }

// ---- Main -------------------------------------------------------------------

async function main() {
  var opts = parseArgs();
  if (opts.showVoices) return browseVoices(opts.voiceGender, opts.voiceCategory);
  if (opts.showAssignments) return showVoiceAssignments();
  if (opts.listApps) return listApplications();
  if (!opts.configPath) fatal("--config <file> required. Use --help.");

  var config = loadConfig(opts.configPath);
  enforceUniqueVoice(config, opts.configPath);

  console.log("\n  Voice Agent Factory");
  console.log("  -------------------");
  console.log("  Application:  " + (config.product || "?"));
  console.log("  Role:         " + (config.role || "?"));
  if (config.partner) console.log("  Partner:      " + config.partner);
  console.log("  Agent:        " + config.agent_name);
  if (config.widget_embed) console.log("  Widget:       yes (chat embed)");
  console.log("  Voice:        " + config.voice_id);
  console.log("  Collection:   " + config.collection_id);
  console.log("  Bridge:       " + config.bridge_url);
  console.log("  Phone:        " + (config.twilio_phone_number || "(none)"));
  console.log();

  if (opts.dryRun) {
    console.log("  === DRY RUN ===");
    console.log("  Prompt: " + config.system_prompt.length + " chars");
    console.log("  === End ===\n");
    return;
  }

  if (!ELEVENLABS_API_KEY) fatal("ELEVENLABS_API_KEY not set");

  var agentId = await createAgent(config);
  var toolId = await createTool(config);
  await attachToolToAgent(agentId, toolId);
  var phoneId = await importPhoneNumber(config);
  await assignPhoneToAgent(phoneId, agentId);

  var result = {
    agent_id: agentId, tool_id: toolId, phone_number_id: phoneId,
    voice_id: config.voice_id, product: config.product, role: config.role,
    partner: config.partner || null,
    widget_embed: config.widget_embed || false,
    collection_id: config.collection_id, config_file: path.resolve(opts.configPath),
    created_at: new Date().toISOString()
  };
  if (config.widget_embed) {
    result.widget_snippet = "<elevenlabs-convai agent-id=\"" + agentId + "\"></elevenlabs-convai>\n<script src=\"https://elevenlabs.io/convai-widget/index.js\" async type=\"text/javascript\"></script>";
  }
  var outPath = path.join(path.dirname(path.resolve(opts.configPath)),
    path.basename(opts.configPath, ".json") + ".result.json");
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));

  console.log("\n  Done. Result: " + outPath);
  console.log("  Agent ID:  " + agentId);
  console.log("  Voice:     " + config.voice_id);
  if (phoneId) console.log("  Phone:     " + config.twilio_phone_number);
  if (result.widget_snippet) {
    console.log("\n  Widget embed code (paste into partner site):");
    console.log("  " + result.widget_snippet.split("\n").join("\n  "));
  }
  console.log();
}

main().catch(function(e) { console.error(e); process.exit(1); });
