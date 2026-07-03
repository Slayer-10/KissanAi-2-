import sys
import os
import logging
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Force UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

# Configure logging to show info messages
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
import services.stt_service
import services.tts_service

client = TestClient(app)

def run_tests():
    print("="*60)
    print("STARTING FARM AI PUNJABI & SIRAIKI END-TO-END TESTS")
    print("="*60)
    
    mock_audio = b"fake_audio_bytes_for_testing"
    
    # Test Case configurations
    test_cases = [
        {
            "name": "1. Urdu Voice Note",
            "detected_lang": "ur",
            "transcript": "کپاس کے پتوں پر پیلے دھبے ہیں",
            "lang_hint": "ur",
            "expect_lang": "ur"
        },
        {
            "name": "2. Roman Urdu Voice Note",
            "detected_lang": "roman_urdu",
            "transcript": "Meri cotton crop pe peelay nishan hain",
            "lang_hint": "roman_urdu",
            "expect_lang": "roman_urdu"
        },
        {
            "name": "3. English Voice Note",
            "detected_lang": "english",
            "transcript": "My cotton crop leaves are turning yellow",
            "lang_hint": "english",
            "expect_lang": "english"
        },
        {
            "name": "4. Punjabi Voice Note",
            "detected_lang": "punjabi",
            "transcript": "کپاس دے پتے پیلے ہو رہے نے، میں کی کراں؟",
            "lang_hint": "punjabi",
            "expect_lang": "punjabi"
        },
        {
            "name": "5. Siraiki Voice Note",
            "detected_lang": "siraiki",
            "transcript": "آم دے پتیاں تے داغ آ گئے ہن، میں کیا کراں؟",
            "lang_hint": "siraiki",
            "expect_lang": "siraiki"
        }
    ]
    
    for tc in test_cases:
        print(f"\nRunning test: {tc['name']}")
        
        # Mock transcribe_audio to return our configured values
        mock_stt = {
            "success": True,
            "transcript": tc["transcript"],
            "language_hint": tc["detected_lang"],
            "error_type": None,
            "model_used": "mock-gemini-3.5-flash"
        }
        
        with patch("routers.voice.transcribe_audio", return_value=mock_stt):
            response = client.post(
                "/voice-analyze",
                data={
                    "latitude": "31.5204",
                    "longitude": "74.3587",
                    "language_hint": tc["lang_hint"]
                },
                files={"audio": ("voice.wav", mock_audio, "audio/wav")}
            )
            
            print(f"Status Code: {response.status_code}")
            res = response.json()
            assert response.status_code == 200
            
            print(f"Transcript: {res.get('transcript')}")
            print(f"Farmer Response: {res.get('farmer_response')}")
            print(f"TTS Summary: {res.get('tts_summary')}")
            print(f"Audio URL: {res.get('audio_url')}")
            print(f"Voice Status: {res.get('voice_status')}")
            print(f"Gemini Status: {res.get('gemini_status')}")
            
            # Additional assertions
            if tc["expect_lang"] == "punjabi":
                assert "خطرے دی سطح" in res.get("farmer_response") or "تجویز کیتا گیا عمل" in res.get("farmer_response")
                # TTS summary should also have headings, same format as Urdu
                tts = res.get("tts_summary", "")
                assert "ممکنہ مسئلہ" in tts or "خطرے دی سطح" in tts, "Punjabi TTS summary should contain headings like Urdu"
            elif tc["expect_lang"] == "siraiki":
                assert "خطرے دی سطح" in res.get("farmer_response") or "تجویز کیتا گیا عمل" in res.get("farmer_response")
                tts = res.get("tts_summary", "")
                assert "ممکنہ مسئلہ" in tts or "خطرے دی سطح" in tts, "Siraiki TTS summary should contain headings like Urdu"
                
    # 6. Punjabi/Siraiki TTS retry (retry with urdu hint, no Roman conversion)
    print("\n" + "="*60)
    print("6. Punjabi/Siraiki TTS retry (retry with urdu hint)")
    print("="*60)
    
    mock_stt_siraiki = {
        "success": True,
        "transcript": "کپاس دے پتے پیلے ہو رہے نے، میں کی کراں؟",
        "language_hint": "siraiki",
        "error_type": None,
        "model_used": "mock-gemini-3.5-flash"
    }
    
    # We want generate_tts_audio to fail on 'siraiki' input, and succeed on 'urdu' retry
    def mock_generate_tts(text, lang_hint=None):
        if lang_hint == "siraiki":
            print(f"Mock TTS: Simulating failure for dialect={lang_hint}")
            return {"success": False, "error_type": "tts_failed"}
        elif lang_hint == "urdu":
            print(f"Mock TTS: Succeeding for lang_hint={lang_hint} (urdu retry)")
            return {"success": True, "filename": "tts_retry_success.wav"}
        else:
            print(f"Mock TTS: Unexpected lang_hint={lang_hint} for retry test")
            return {"success": False, "error_type": "invalid_lang_hint"}
            
    with patch("routers.voice.transcribe_audio", return_value=mock_stt_siraiki):
        with patch("routers.voice.generate_tts_audio", side_effect=mock_generate_tts):
            response = client.post(
                "/voice-analyze",
                data={
                    "latitude": "31.5204",
                    "longitude": "74.3587",
                    "language_hint": "siraiki"
                },
                files={"audio": ("voice.wav", mock_audio, "audio/wav")}
            )
            
            print(f"Status Code: {response.status_code}")
            res = response.json()
            assert response.status_code == 200
            
            print(f"Transcript: {res.get('transcript')}")
            print(f"Farmer Response: {res.get('farmer_response')}")
            print(f"TTS Summary (should remain Siraiki/Urdu script with headings): {res.get('tts_summary')}")
            print(f"Audio URL: {res.get('audio_url')}")
            print(f"Voice Status: {res.get('voice_status')}")
            assert res.get("voice_status", {}).get("tts_success") is True
            assert "tts_retry_success.wav" in res.get("audio_url")
            # The visible tts_summary must be in Siraiki script and contain headings
            tts = res.get("tts_summary", "")
            assert "ممکنہ مسئلہ" in tts or "خطرے دی سطح" in tts, "Fallback retry tts_summary should still have headings in Siraiki script"
            
    print("\nALL VOICE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
