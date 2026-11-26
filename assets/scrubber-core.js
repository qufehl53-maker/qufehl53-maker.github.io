// Zero-backend, 100% browser-local secret & PII scrubber engine with deterministic tokenization & round-trip rehydration.
(function (root) {
  const DEFAULT_RULES = [
    {
      id: "private_key",
      label: "PEM Private Keys",
      tokenPrefix: "PRIVATE_KEY",
      enabled: true,
      regex: /-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----/g
    },
    {
      id: "openai_anthropic",
      label: "OpenAI / Anthropic Keys",
      tokenPrefix: "AI_API_KEY",
      enabled: true,
      regex: /\b(?:sk-ant-api\d{2}-[A-Za-z0-9_-]{20,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,})\b/g
    },
    {
      id: "google_api",
      label: "Google / Gemini API Keys",
      tokenPrefix: "GCP_API_KEY",
      enabled: true,
      regex: /\bAIza[0-9A-Za-z_-]{35}\b/g
    },
    {
      id: "github",
      label: "GitHub Tokens (ghp/pat)",
      tokenPrefix: "GITHUB_TOKEN",
      enabled: true,
      regex: /\b(?:gh[pousr]_[A-Za-z0-9_]{30,255}|github_pat_[A-Za-z0-9_]{22,255})\b/g
    },
    {
      id: "aws_key",
      label: "AWS Access Key IDs",
      tokenPrefix: "AWS_KEY_ID",
      enabled: true,
      regex: /\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b/g
    },
    {
      id: "slack_stripe",
      label: "Slack & Stripe Keys",
      tokenPrefix: "SAAS_TOKEN",
      enabled: true,
      regex: /\b(?:xox[baprs]-[0-9A-Za-z-]{10,}|(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,})\b/g
    },
    {
      id: "jwt",
      label: "JWT Tokens",
      tokenPrefix: "JWT",
      enabled: true,
      regex: /\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g
    },
    {
      id: "url_creds",
      label: "URLs with Credentials",
      tokenPrefix: "URL_SECRET",
      enabled: true,
      // Captures protocol://user:PASS@host and replaces only PASS
      customReplace: function (text, getToken) {
        return text.replace(/([a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^:\s\/]+:)([^@\s\/]+)(@)/g, function (_, p1, secret, p3) {
          if (/^\[[A-Z0-9_]+_\d+\]$/.test(secret)) return _;
          return p1 + getToken("URL_PASS", secret) + p3;
        });
      }
    },
    {
      id: "bearer_header",
      label: "Authorization / Bearer Headers",
      tokenPrefix: "AUTH_SECRET",
      enabled: true,
      customReplace: function (text, getToken) {
        return text.replace(/((?:Authorization|X-API-Key)\s*[:=]\s*(?:Bearer\s+|Basic\s+)?)([A-Za-z0-9._~+\/-]{12,}=*)/gi, function (_, prefix, secret) {
          if (/^\[[A-Z0-9_]+_\d+\]$/.test(secret)) return _;
          return prefix + getToken("AUTH_SECRET", secret);
        });
      }
    },
    {
      id: "env_kv",
      label: ".env / Config Secret Assignments",
      tokenPrefix: "CONFIG_SECRET",
      enabled: true,
      customReplace: function (text, getToken) {
        return text.replace(/(\b[A-Za-z0-9_]*(?:PASSWORD|PASSWD|SECRET|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_TOKEN|AUTH_TOKEN|CLIENT_SECRET|DB_PASS)[A-Za-z0-9_]*\b\s*[:=]\s*["']?)([^"'\s,;}{]+)(["']?)/gi, function (full, k, val, q) {
          if (!val || val.length < 4 || /^(?:true|false|null|none|undefined|\$[A-Za-z0-9_{}]+|\[[A-Z0-9_]+_\d+\])$/i.test(val)) {
            return full;
          }
          return k + getToken("CONFIG_SECRET", val) + q;
        });
      }
    },
    {
      id: "email",
      label: "Email Addresses",
      tokenPrefix: "EMAIL",
      enabled: true,
      regex: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g
    },
    {
      id: "ipv4",
      label: "IPv4 Addresses (excl. localhost)",
      tokenPrefix: "IPV4",
      enabled: true,
      customReplace: function (text, getToken, opts) {
        return text.replace(/\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g, function (ip) {
          if (opts && opts.keepLocalhost && (ip === "127.0.0.1" || ip === "0.0.0.0")) {
            return ip;
          }
          return getToken("IPV4", ip);
        });
      }
    },
    {
      id: "evm_wallet",
      label: "Crypto Addresses (0x EVM)",
      tokenPrefix: "WALLET",
      enabled: false,
      regex: /\b0x[a-fA-F0-9]{40}\b/g
    }
  ];

  function scrubText(inputText, options) {
    const opts = Object.assign({
      enabledIds: null, // null = use rule.enabled
      keepLocalhost: true,
      customTerms: [], // array of strings
      customRegex: ""
    }, options || {});

    const valueToToken = new Map();
    const tokenToValue = {};
    const countsByPrefix = {};
    const statsByPrefix = {};
    let totalReplacements = 0;

    function getToken(prefix, rawValue) {
      totalReplacements++;
      statsByPrefix[prefix] = (statsByPrefix[prefix] || 0) + 1;
      if (valueToToken.has(rawValue)) {
        return valueToToken.get(rawValue);
      }
      const nextIdx = (countsByPrefix[prefix] || 0) + 1;
      countsByPrefix[prefix] = nextIdx;
      const token = "[" + prefix + "_" + nextIdx + "]";
      valueToToken.set(rawValue, token);
      tokenToValue[token] = rawValue;
      return token;
    }

    let output = String(inputText || "");

    // 1. Custom exact terms first
    if (Array.isArray(opts.customTerms) && opts.customTerms.length > 0) {
      opts.customTerms.forEach(function (term) {
        const clean = String(term || "").trim();
        if (!clean) return;
        const escaped = clean.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        output = output.replace(new RegExp(escaped, "g"), function (m) {
          return getToken("CUSTOM", m);
        });
      });
    }

    // 2. Custom regex
    if (opts.customRegex && opts.customRegex.trim()) {
      try {
        const rx = new RegExp(opts.customRegex.trim(), "g");
        output = output.replace(rx, function (m) {
          if (!m) return m;
          return getToken("CUSTOM_RX", m);
        });
      } catch (err) {
        // Invalid user regex ignored safely; caller can validate separately
      }
    }

    // 3. Built-in rules
    DEFAULT_RULES.forEach(function (rule) {
      const isEnabled = opts.enabledIds ? opts.enabledIds.includes(rule.id) : rule.enabled;
      if (!isEnabled) return;
      if (typeof rule.customReplace === "function") {
        output = rule.customReplace(output, getToken, opts);
      } else if (rule.regex) {
        const rx = new RegExp(rule.regex.source, rule.regex.flags);
        output = output.replace(rx, function (match) {
          if (/^\[[A-Z0-9_]+_\d+\]$/.test(match)) return match;
          return getToken(rule.tokenPrefix, match);
        });
      }
    });

    return {
      output: output,
      map: tokenToValue,
      uniqueCount: Object.keys(tokenToValue).length,
      totalReplacements: totalReplacements,
      statsByPrefix: statsByPrefix
    };
  }

  function rehydrateText(scrubbedText, tokenMap) {
    let text = String(scrubbedText || "");
    if (!tokenMap || typeof tokenMap !== "object") return text;
    Object.keys(tokenMap).forEach(function (token) {
      const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      text = text.replace(new RegExp(escaped, "g"), function () {
        return tokenMap[token];
      });
    });
    return text;
  }

  root.SurohScrubber = {
    DEFAULT_RULES: DEFAULT_RULES,
    scrubText: scrubText,
    rehydrateText: rehydrateText
  };
})(typeof window !== "undefined" ? window : globalThis);
