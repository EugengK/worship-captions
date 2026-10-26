import os, wave
from google import genai
from google.genai import types
c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
text = ("오늘 우리는 창세기 12장 1절 말씀을 함께 묵상하겠습니다. "
        "여호와께서 아브람에게 이르시되, 너는 너의 고향과 친척과 아버지의 집을 떠나 내가 네게 보여 줄 땅으로 가라. "
        "하나님은 언약을 맺으시는 분이십니다. 우리가 의롭다 하심을 받는 것은 오직 믿음으로 말미암습니다. "
        "하이델베르크 요리문답 제1문은 묻습니다. 살아서나 죽어서나 당신의 유일한 위로는 무엇입니까?")
r = c.models.generate_content(model="gemini-3.8-flash-tts", contents="차분한 설교 톤으로 읽어 주세요: " + text,
    config=types.GenerateContentConfig(response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")))))
p = r.candidates[0].content.parts[0].inline_data
print(p.mime_type, len(p.data))
with wave.open("out/ko_sermon.wav","wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(p.data)
