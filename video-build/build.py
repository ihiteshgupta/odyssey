#!/usr/bin/env python3
"""Programmatic Odyssey demo video: styled HTML slides + Google Cloud TTS (Studio
voice) AI voiceover, assembled into a 1080p MP4 with ffmpeg. macOS `say` fallback."""
import os, subprocess, json, pathlib, base64, urllib.request, time

ROOT = pathlib.Path(__file__).resolve().parent
SLIDES, AUDIO, CLIPS = ROOT / "slides", ROOT / "audio", ROOT / "clips"
for d in (SLIDES, AUDIO, CLIPS): d.mkdir(exist_ok=True)
HS = (pathlib.Path.home() /
      "Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-arm64/chrome-headless-shell")
VOICE, RATE = "Samantha", 168           # macOS say fallback
GVOICE, PROJECT = "en-US-Studio-O", "odyssey-hackathon-498211"
OUT = ROOT / "odyssey-demo.mp4"

_env = {**os.environ, "CLOUDSDK_CONFIG": os.path.expanduser("~/.config/gcloud-odyssey")}
TOKEN = subprocess.run(["gcloud", "auth", "print-access-token"], env=_env,
                       capture_output=True, text=True).stdout.strip()

def tts(text, out_mp3):
    """Google Cloud TTS Studio voice -> MP3 (retry on transient rate caps);
    fall back to macOS say (AIFF) only if all retries fail."""
    body = json.dumps({"input": {"text": text},
                       "voice": {"languageCode": "en-US", "name": GVOICE},
                       "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.0}}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize",
                                         data=body, headers={"Authorization": f"Bearer {TOKEN}",
                                         "Content-Type": "application/json; charset=utf-8",
                                         "x-goog-user-project": PROJECT})
            audio = json.loads(urllib.request.urlopen(req, timeout=90).read())["audioContent"]
            out_mp3.write_bytes(base64.b64decode(audio))
            return out_mp3
        except Exception as e:
            print(f"  TTS attempt {attempt+1} failed ({e}); backing off")
            time.sleep(6 * (attempt + 1))
    print("  TTS fallback to say")
    aiff = out_mp3.with_suffix(".aiff")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), text], check=True)
    return aiff

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden}
body{position:relative;font-family:-apple-system,'SF Pro Display',system-ui,sans-serif;
 background:radial-gradient(1300px 850px at 72% 16%, #16204a 0%, #0b1020 55%, #060812 100%);color:#e8eefc}
.wrap{position:relative;width:100%;height:100%;padding:108px 132px;display:flex;flex-direction:column;justify-content:center}
.kicker{color:#7dd3fc;font-weight:700;letter-spacing:4px;text-transform:uppercase;font-size:29px;margin-bottom:26px}
h1{font-size:84px;font-weight:800;line-height:1.06;letter-spacing:-1px}
h2{font-size:62px;font-weight:800;line-height:1.12;letter-spacing:-.5px}
.accent{color:#7dd3fc}.tealtxt{color:#5eead4}
.sub{font-size:37px;color:#aebbd6;margin-top:30px;line-height:1.42;font-weight:500}
.metrics{display:flex;gap:30px;margin-top:60px}
.metric{background:rgba(125,211,252,.07);border:1px solid rgba(125,211,252,.22);border-radius:22px;padding:40px 40px;flex:1}
.metric .n{font-size:74px;font-weight:800;color:#5eead4;line-height:1}
.metric .l{font-size:25px;color:#aebbd6;margin-top:14px;font-weight:600;line-height:1.3}
.ba{display:flex;gap:38px;margin-top:54px}
.col{flex:1;border-radius:20px;padding:36px 38px}
.before{background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.32)}
.after{background:rgba(94,234,212,.08);border:1px solid rgba(94,234,212,.32)}
.col .h{font-size:25px;letter-spacing:2px;text-transform:uppercase;font-weight:700;margin-bottom:18px}
.before .h{color:#fca5a5}.after .h{color:#5eead4}
.col .t{font-size:33px;line-height:1.38;font-weight:600;color:#e8eefc}
.badge{display:inline-block;background:rgba(94,234,212,.12);border:1px solid rgba(94,234,212,.4);color:#5eead4;
 border-radius:999px;padding:14px 34px;font-size:31px;font-weight:700}
.disc{position:absolute;bottom:46px;left:132px;right:132px;font-size:23px;color:#67769c;line-height:1.4}
b{color:#fff}
"""

SCENES = [
 ("s1",
  "This is Odyssey — autonomous corporate travel that finance can actually approve. "
  "And here's the proof, not the adjectives. A hundred percent guardrail block-rate. "
  "Zero false bookings. Zero over-budget checkouts. Seventy-eight tests green. "
  "Let me show you how I made an existing agent provably reliable.",
  '<div class="wrap"><div class="kicker">Google AI Agents Challenge &middot; Track 2 — Optimize</div>'
  '<h1>Odyssey<br><span class="accent">autonomous corporate travel,<br>with a trust layer</span></h1>'
  '<div class="metrics">'
  '<div class="metric"><div class="n">100%</div><div class="l">guardrail block-rate</div></div>'
  '<div class="metric"><div class="n">0</div><div class="l">false bookings</div></div>'
  '<div class="metric"><div class="n">0</div><div class="l">over-budget checkouts</div></div>'
  '<div class="metric"><div class="n">78</div><div class="l">tests green</div></div></div></div>'),

 ("s2",
  "Odyssey books a complete multi-vendor trip in one conversation. A planner agent on Google's "
  "A D K and Gemini 2.5 Flash negotiates each slice cross-process over the A2A protocol with three "
  "independent merchant agents, settles over U C P, and signs every booking as an A P 2 mandate chain. "
  "Four services, live on Cloud Run.",
  '<div class="wrap"><div class="kicker">Live on Google Cloud Run &middot; asia-south1</div>'
  '<h2 style="font-size:54px">Multi-agent — deployed &amp; running</h2>'
  '<div style="margin-top:32px;align-self:center;border-radius:16px;overflow:hidden;border:1px solid rgba(125,211,252,.35);box-shadow:0 24px 70px rgba(0,0,0,.55);max-width:1480px">'
  '<img src="assets/concierge.png" style="width:100%;display:block"/></div>'
  '<div class="sub" style="margin-top:28px;font-size:31px">Concierge (ADK &middot; Gemini 2.5 Flash) negotiates flights, hotel &amp; activities cross-process over <span class="accent">A2A</span> with 3 merchant agents, settles over <span class="accent">UCP</span>, signs every booking as an <span class="accent">AP2</span> mandate chain.</div></div>'),

 ("s3",
  "For the Optimize track, the headline is a bug hunt. An in-process fallback was silently masking "
  "real cross-service failures — my tests were green while the agents never actually negotiated between "
  "services. So I worked honest-tests-first: make the failure visible, then fix the root cause. "
  "Three chained bugs, fixed — and the real cross-process call is now proven in the logs.",
  '<div class="wrap"><div class="kicker">The headline optimization</div>'
  '<h2>The &ldquo;A2A 3-bug cascade&rdquo;</h2>'
  '<div class="ba"><div class="col before"><div class="h">Before</div>'
  '<div class="t">An in-process fallback silently <b>masked</b> real cross-service failures. Tests were green — the agents never actually negotiated.</div></div>'
  '<div class="col after"><div class="h">After</div>'
  '<div class="t">Honest-tests-first: made the failure <b>visible</b>, fixed 3 chained bugs. Real cross-process A2A now proven in the logs.</div></div></div>'
  '<div class="sub" style="margin-top:42px">commits <span class="accent">88988d8 &rarr; 24d7030 &rarr; 1b80d5e</span></div></div>'),

 ("s4",
  "The evaluation told the same story in miniature. Running Google's A D K eval live, it scored zero — "
  "my expected trajectory was stale and the text-match metric brittle. So I regenerated the eval from real "
  "runs and switched to a semantic judge. Now it passes reliably. The eval, doing its job.",
  '<div class="wrap"><div class="kicker">Rigorous evaluation</div>'
  '<h2>I caught my own eval lying</h2>'
  '<div class="ba"><div class="col before"><div class="h">Before</div>'
  '<div class="t">ADK eval scored <b>0.0</b> — stale expected trajectory, brittle text-overlap metric.</div></div>'
  '<div class="col after"><div class="h">After</div>'
  '<div class="t">Regenerated from real runs + a semantic <b>final_response_match_v2</b> judge &rarr; reliably <b>green</b>.</div></div></div>'
  '<div class="sub" style="margin-top:42px">The eval doing its job — the deterministic safety eval stays green throughout.</div></div>'),

 ("s5",
  "I hardened the negotiation with bounded retries and a strict mode that surfaces failures instead of "
  "hiding them, wired the eval into C I, and instrumented per-turn cost, latency, and token usage with "
  "Cloud Trace. Reliability as an engineering discipline.",
  '<div class="wrap"><div class="kicker">AI quality as an engineering discipline</div>'
  '<h2>Hardened &amp; observable</h2>'
  '<div class="metrics" style="margin-top:56px">'
  '<div class="metric"><div style="font-size:38px;font-weight:800;color:#5eead4">Retry + strict mode</div>'
  '<div class="l" style="margin-top:14px;font-size:26px">bounded backoff; surfaces failures instead of masking them</div></div>'
  '<div class="metric"><div style="font-size:38px;font-weight:800;color:#5eead4">ADK eval in CI</div>'
  '<div class="l" style="margin-top:14px;font-size:26px">every push gated on the eval</div></div>'
  '<div class="metric"><div style="font-size:38px;font-weight:800;color:#5eead4">Cloud Trace</div>'
  '<div class="l" style="margin-top:14px;font-size:26px">per-turn cost &middot; latency &middot; tokens</div></div></div></div>'),

 ("s6",
  "The trust spine is what makes it safe. A deny-by-default budget guardrail that fails closed. "
  "A human-confirmation gate the agent cannot skip. And an A P 2 signed-mandate chain for a "
  "non-repudiable audit trail. The agent literally cannot spend money it wasn't authorized to.",
  '<div class="wrap"><div class="kicker">The trust spine</div>'
  '<h2>It <span class="accent">cannot</span> spend money it wasn&rsquo;t authorized to</h2>'
  '<div class="ba"><div class="col after" style="background:rgba(125,211,252,.07);border-color:rgba(125,211,252,.32)">'
  '<div class="h" style="color:#7dd3fc">Deny-by-default guardrail</div><div class="t">fails <b>closed</b> on missing budget</div></div>'
  '<div class="col after" style="background:rgba(125,211,252,.07);border-color:rgba(125,211,252,.32)">'
  '<div class="h" style="color:#7dd3fc">Non-skippable HITL</div><div class="t">a human confirms every booking</div></div>'
  '<div class="col after" style="background:rgba(125,211,252,.07);border-color:rgba(125,211,252,.32)">'
  '<div class="h" style="color:#7dd3fc">AP2 mandate chain</div><div class="t">non-repudiable audit trail</div></div></div></div>'),

 ("s7",
  "The buyer isn't shopping for a travel bot — they want a governance artifact. A-PAC mid-market firms "
  "lose ten to twenty percent of travel spend to out-of-policy bookings, with no audit trail for finance. "
  "Odyssey is the first-mover native build on Google's own A2A, U C P, and A P 2 stack. Friction is the feature.",
  '<div class="wrap"><div class="kicker">The business case</div>'
  '<h2>A governance artifact, not a travel bot</h2>'
  '<div class="sub" style="margin-top:36px">APAC mid-market firms lose <span class="accent">10–20%</span> of travel spend to out-of-policy bookings — with no audit trail for finance.</div>'
  '<div style="margin-top:48px"><span class="badge">First-mover native build on Google&rsquo;s A2A &middot; UCP &middot; AP2 stack</span></div>'
  '<div class="sub" style="margin-top:34px;font-size:40px;color:#e8eefc;font-weight:700">Friction is the feature.</div></div>'),

 ("s8",
  "Odyssey. Every tool call, every booking, every denial — logged, signed, and auditable. "
  "Autonomous travel a C F O can sign off on. Thank you.",
  '<div class="wrap" style="text-align:center;align-items:center">'
  '<h1>Every tool call. Every booking.<br>Every denial — <span class="accent">logged, signed, auditable.</span></h1>'
  '<div class="sub" style="margin-top:38px">Autonomous travel a CFO can sign off on.</div>'
  '<div style="margin-top:50px"><span class="badge" style="font-size:30px">github.com/ihiteshgupta/odyssey</span></div>'
  '<div class="disc" style="text-align:center">AP2 payment signing is simulated (STUB-SIG SHA-256, not ECDSA P-256) — no real money moves. Server-side mandate verification genuinely runs.</div></div>'),
]

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"FAIL: {' '.join(cmd[:3])}...\n{r.stderr[-800:]}")
    return r

def dur(path):
    r = run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(path)])
    return float(r.stdout.strip())

clip_list = []
for sid, narr, body in SCENES:
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    hp = ROOT / f"{sid}.html"; hp.write_text(html)
    png = SLIDES / f"{sid}.png"
    run([str(HS),"--headless","--no-sandbox","--disable-gpu","--hide-scrollbars",
         "--force-device-scale-factor=1","--window-size=1920,1080",
         f"--virtual-time-budget=2500",f"--screenshot={png}",f"file://{hp}"])
    audio = tts(narr, AUDIO / f"{sid}.mp3")
    total = round(dur(audio) + 0.75, 2)
    fout = round(total - 0.5, 2)
    clip = CLIPS / f"{sid}.mp4"
    run(["ffmpeg","-y","-loop","1","-i",str(png),"-i",str(audio),
         "-filter_complex",
         f"[0:v]scale=1920:1080,fps=30,fade=t=in:st=0:d=0.4,fade=t=out:st={fout}:d=0.5,format=yuv420p[v];[1:a]apad[a]",
         "-map","[v]","-map","[a]","-t",str(total),
         "-c:v","libx264","-preset","medium","-crf","20","-c:a","aac","-b:a","192k",str(clip)])
    clip_list.append((sid, clip, total))
    print(f"{sid}: slide+voice+clip {total}s")

listfile = ROOT / "concat.txt"
listfile.write_text("".join(f"file '{c}'\n" for _, c, _ in clip_list))
run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listfile),
     "-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p",
     "-c:a","aac","-b:a","192k","-movflags","+faststart",str(OUT)])
print("TOTAL:", round(sum(t for *_ , t in clip_list), 1), "s  ->", OUT)
print("FINAL_DURATION:", round(dur(OUT), 1), "s")
