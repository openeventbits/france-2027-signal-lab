/* Generated browser asset template. Source: poll_studies.py and its pinned JSON. */
(() => {
  "use strict";
  const binding = /* REVIEWED_STUDY_BINDING */;
  const members = new Map(binding.members.map(member => [member.event_id, member]));

  // SHA-256 of ASCII canonical JSON. No network, platform crypto or raw mutation.
  const K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const rotate = (x, n) => (x >>> n) | (x << (32 - n));
  function digest(text) {
    const bytes = Array.from(text, c => c.charCodeAt(0));
    const bits = bytes.length * 8;
    bytes.push(128);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (let n = 7; n >= 0; n--) bytes.push(Math.floor(bits / 2 ** (8 * n)) & 255);
    const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    for (let offset = 0; offset < bytes.length; offset += 64) {
      const w = new Array(64);
      for (let i = 0; i < 16; i++) w[i] = (bytes[offset+4*i]<<24) | (bytes[offset+4*i+1]<<16) | (bytes[offset+4*i+2]<<8) | bytes[offset+4*i+3];
      for (let i = 16; i < 64; i++) {
        const x = w[i-15], y = w[i-2];
        w[i] = (w[i-16] + (rotate(x,7)^rotate(x,18)^(x>>>3)) + w[i-7] + (rotate(y,17)^rotate(y,19)^(y>>>10))) | 0;
      }
      let [a,b,c,d,e,f,g,j] = h;
      for (let i = 0; i < 64; i++) {
        const t1 = (j + (rotate(e,6)^rotate(e,11)^rotate(e,25)) + ((e&f)^(~e&g)) + K[i] + w[i]) | 0;
        const t2 = ((rotate(a,2)^rotate(a,13)^rotate(a,22)) + ((a&b)^(a&c)^(b&c))) | 0;
        j=g; g=f; f=e; e=(d+t1)|0; d=c; c=b; b=a; a=(t1+t2)|0;
      }
      [a,b,c,d,e,f,g,j].forEach((value,i) => { h[i]=(h[i]+value)|0; });
    }
    return h.map(x => (x>>>0).toString(16).padStart(8,"0")).join("");
  }
  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (value && typeof value === "object") return "{" + Object.keys(value).sort().map(key => canonical(key)+":"+canonical(value[key])).join(",") + "}";
    return JSON.stringify(value).replace(/[\u0080-\uffff]/g, c => "\\u"+c.charCodeAt(0).toString(16).padStart(4,"0"));
  }
  // Cache by full object serialization, never only by ID or mutable reference.
  const authenticated = new Set();
  function member(event) {
    const record = members.get(event?.event_id);
    if (!record) return null;
    const serialized = canonical(event);
    if (!authenticated.has(serialized)) {
      if (digest(serialized) !== record.browser_object_sha256) throw new Error("Reviewed polling study event changed: " + event.event_id);
      authenticated.add(serialized);
    }
    return record;
  }
  function pollster(event) { return member(event) ? binding.canonical_pollster : event.pollster; }
  function key(event) { return [pollster(event),event.fieldwork_start,event.fieldwork_end,event.sample_size ?? null]; }
  function verifyCollection(events) {
    const ids = events.map(e => e.event_id);
    if (ids.some(id => members.has(id)) && [...members.keys()].some(id => ids.filter(x => x === id).length !== 1)) {
      throw new Error("Reviewed polling study requires its three exact events");
    }
    events.forEach(member);
    if (ids.some(id => members.has(id))) {
      const expectedKey = JSON.stringify([binding.canonical_pollster,binding.fieldwork_start,binding.fieldwork_end,binding.sample_size]);
      if (events.some(event => !members.has(event.event_id) && JSON.stringify(key(event)) === expectedKey)) {
        throw new Error("Unreviewed event collides with the authenticated polling study");
      }
    }
  }
  globalThis.FR27PollStudies = Object.freeze({pollster,key,member,verifyCollection,
    order(event) { return member(event)?.canonical_anchor_index ?? 0; }});
})();
