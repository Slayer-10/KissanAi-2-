import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';

const ROMAN_URDU_LINES = [
  "Aapka sawal samjha ja raha hai...",
  "Fasal aur masla check ho raha hai...",
  "Mausam aur location dekhi ja rahi hai...",
  "Knowledge base se maloomat li ja rahi hain...",
  "Spray aur pani ka plan tayyar ho raha hai...",
  "Final jawab tayyar ho raha hai..."
];

const URDU_SCRIPT_LINES = [
  "آپ کا سوال سمجھا جا رہا ہے...",
  "فصل اور مسئلہ چیک کیا جا رہا ہے...",
  "موسم اور لوکیشن دیکھی جا رہی ہے...",
  "نالج بیس سے معلومات لی جا رہی ہیں...",
  "سپرے اور پانی کا منصوبہ تیار ہو رہا ہے...",
  "حتمی جواب تیار ہو رہا ہے..."
];

const ENGLISH_LINES = [
  "Understanding your query...",
  "Checking crop and issue...",
  "Checking weather and location...",
  "Searching the knowledge base...",
  "Preparing spray and water advice...",
  "Final answer is getting ready..."
];

const ROMAN_URDU_VOICE_LINES = [
  "Aapki awaz suni ja rahi hai...",
  "Voice note ko alfaaz mein badla ja raha hai...",
  "KisaanAI maslay ko samajh raha hai...",
  "Fasal, mausam aur mashwara check ho raha hai...",
  "Aapke liye jawab tayyar ho raha hai...",
  "Voice reply bas tayyar hai..."
];

const URDU_SCRIPT_VOICE_LINES = [
  "آپ کی آواز سنی جا رہی ہے...",
  "وائس نوٹ کو الفاظ میں بدلا جا رہا ہے...",
  "کسان AI مسئلہ سمجھ رہا ہے...",
  "فصل، موسم اور مشورہ چیک ہو رہا ہے...",
  "آپ کے لیے جواب تیار ہو رہا ہے...",
  "وائس جواب بس تیار ہے..."
];

const ENGLISH_VOICE_LINES = [
  "Listening to your voice note...",
  "Turning your voice into words...",
  "KisaanAI is understanding the issue...",
  "Checking crop, weather, and advice...",
  "Preparing your answer...",
  "Voice reply is almost ready..."
];

function detectQueryLanguage(text) {
  if (!text || typeof text !== 'string') return 'roman_urdu';
  
  // 1. Urdu Arabic-script characters check
  if (/[\u0600-\u06FF]/.test(text)) {
    return 'urdu';
  }
  
  // 2. Mostly English words check
  const textLower = text.toLowerCase();
  const words = textLower.match(/\b[a-z']+\b/g) || [];
  if (words.length === 0) return 'roman_urdu';
  
  const englishWords = [
    "crop", "plant", "leaf", "leaves", "pest", "fertilizer", "soil", 
    "irrigation", "disease", "fungus", "water", "spray", "hello", "hi", 
    "help", "problem", "weather", "rain", "temperature", "humidity",
    "my", "is", "the", "are", "have", "has", "of", "and", "in", "to", "it", "you"
  ];
  
  const romanUrduWords = [
    "meri", "mera", "mere", "fasal", "kapas", "kapaas", "gandum", "aam", 
    "patton", "pattay", "peelay", "nishan", "daag", "masla", "pani", 
    "khad", "keera", "keeray", "bimari", "spray", "zameen", "mitti",
    "yeh", "hai", "hain", "ke", "ki", "ka", "aur", "pe", "par", "ko",
    "kya", "kyun", "kab", "kese", "karna", "krna", "he", "rha", "rhi",
    "batao", "bataen"
  ];
  
  let englishHits = 0;
  let romanUrduHits = 0;
  
  for (const word of words) {
    if (englishWords.includes(word)) englishHits++;
    if (romanUrduWords.includes(word)) romanUrduHits++;
  }
  
  if (englishHits > romanUrduHits) {
    return 'english';
  } else if (romanUrduHits > englishHits) {
    return 'roman_urdu';
  }
  
  return 'roman_urdu';
}

export default function LoadingSpinner({ queryText, isVoice, chatMessages }) {
  // Determine language
  let lang = 'roman_urdu';
  if (isVoice) {
    // For voice, try to detect language from the last user text message in chatMessages
    if (chatMessages && chatMessages.length > 0) {
      for (let i = chatMessages.length - 1; i >= 0; i--) {
        const msg = chatMessages[i];
        if (msg.type === 'user' && msg.text && msg.text !== 'آواز ریکارڈنگ...' && msg.text !== 'تصویر بھیجی گئی') {
          lang = detectQueryLanguage(msg.text);
          break;
        }
      }
    }
  } else {
    lang = detectQueryLanguage(queryText);
  }

  let loadingLines = ROMAN_URDU_LINES;
  if (isVoice) {
    if (lang === 'urdu') {
      loadingLines = URDU_SCRIPT_VOICE_LINES;
    } else if (lang === 'english') {
      loadingLines = ENGLISH_VOICE_LINES;
    } else {
      loadingLines = ROMAN_URDU_VOICE_LINES;
    }
  } else {
    if (lang === 'urdu') {
      loadingLines = URDU_SCRIPT_LINES;
    } else if (lang === 'english') {
      loadingLines = ENGLISH_LINES;
    }
  }

  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setCurrentIndex((prevIndex) => {
        if (prevIndex < loadingLines.length - 1) {
          return prevIndex + 1;
        }
        return prevIndex; // Keep showing the final step if request takes longer
      });
    }, 3000); // 3 seconds interval

    return () => {
      clearInterval(intervalId);
    };
  }, [loadingLines]);

  return (
    <View style={styles.container}>
      <Text style={styles.text}>
        {loadingLines[currentIndex]}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 24,
  },
  text: {
    fontSize: 15,
    color: '#888',
    textAlign: 'center',
    lineHeight: 24,
  },
});
