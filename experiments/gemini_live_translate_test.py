import os, sys, asyncio, wave, time
import numpy as np
from google import genai
from google.genai import types

target = sys.argv[1]
w = wave.open("out/ko_sermon.wav"); sr = w.getframerate()
pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
# resample 24k -> 16k (linear)
n16 = int(len(pcm) * 16000 / sr)
pcm16 = np.interp(np.linspace(0, len(pcm)-1, n16), np.arange(len(pcm)), pcm).astype(np.int16).tobytes()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
cfg = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    translation_config=types.TranslationConfig(target_language_code=target),
)

async def main():
    t0 = time.time(); first_out = None
    src, out, audio = [], [], bytearray()
    async with client.aio.live.connect(model="gemini-3.5-live-translate-preview", config=cfg) as s:
        async def send():
            chunk = 3200  # 100 ms
            for i in range(0, len(pcm16), chunk):
                await s.send_realtime_input(audio=types.Blob(data=pcm16[i:i+chunk], mime_type="audio/pcm;rate=16000"))
                await asyncio.sleep(0.1)
            silence = b"\0" * 3200
            for _ in range(40):
                await s.send_realtime_input(audio=types.Blob(data=silence, mime_type="audio/pcm;rate=16000"))
                await asyncio.sleep(0.1)
        async def recv():
            nonlocal first_out
            async for m in s.receive():
                sc = m.server_content
                if not sc: continue
                if sc.input_transcription and sc.input_transcription.text: src.append(sc.input_transcription.text)
                if sc.output_transcription and sc.output_transcription.text:
                    if first_out is None: first_out = time.time() - t0
                    out.append(sc.output_transcription.text)
                if sc.model_turn:
                    for p in sc.model_turn.parts:
                        if p.inline_data: audio.extend(p.inline_data.data)
        r = asyncio.create_task(recv())
        await send()
        await asyncio.sleep(3)
        r.cancel()
    print("== target:", target)
    print("first translated text after (s):", round(first_out,1) if first_out else None)
    print("SOURCE:", "".join(src))
    print("OUTPUT:", "".join(out))
    print("audio bytes:", len(audio))
    if audio:
        with wave.open(f"out/translated_{target}.wav","wb") as o:
            o.setnchannels(1); o.setsampwidth(2); o.setframerate(24000); o.writeframes(bytes(audio))
asyncio.run(main())
