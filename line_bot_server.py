# -*- coding: utf-8 -*-
import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
import threading
from flask import Flask, request

app = Flask(__name__)

# 🔑 LINE & Gemini API Credentials
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ALLOWED_USER_ID = os.environ.get("ALLOWED_USER_ID", "")

# 🧠 หน่วยความจำสถานะการคุยของผู้เล่น (Conversation Session State)
user_states = {}

# ✉️ Helper Function: Reply Message
def reply_message(reply_token, messages):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    
    formatted_messages = []
    for msg in messages[:5]:
        if isinstance(msg, dict):
            formatted_messages.append(msg)
        else:
            formatted_messages.append({"type": "text", "text": str(msg)})
            
    payload = {
        "replyToken": reply_token,
        "messages": formatted_messages
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print(f"Reply failed: {e}")

# 📋 Helper Function: Create Quick Reply Message Object
def make_quick_reply_message(text, options):
    items = []
    for opt in options:
        items.append({
            "type": "action",
            "action": {
                "type": "message",
                "label": opt[:20],  # LINE label character limit is 20
                "text": opt
            }
        })
    return {
        "type": "text",
        "text": text,
        "quickReply": {
            "items": items
        }
    }

# ✂️ Helper Function: Split Long Messages (ป้องกันเกินลิมิต 5,000 ตัวอักษรของ LINE)
def split_message(text, max_len=4500):
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 > max_len:
            if current_part:
                parts.append(current_part)
                current_part = line
            else:
                parts.append(line[:max_len])
                current_part = line[max_len:]
        else:
            if current_part:
                current_part += "\n" + line
            else:
                current_part = line
    if current_part:
        parts.append(current_part)
    return parts

# ✉️ Helper Function: Push Message (ส่งข้อความขนาดยาวแยกทีละสเต็ป)
def push_message(user_id, messages):
    expanded_messages = []
    for msg in messages:
        expanded_messages.extend(split_message(msg))
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    for i in range(0, len(expanded_messages), 5):
        chunk = expanded_messages[i:i+5]
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": msg} for msg in chunk]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                pass
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"Push failed (HTTP {e.code}): {e.reason}")
            print(f"Error Details: {error_body}")
        except Exception as e:
            print(f"Push failed: {e}")

# 🧠 Helper Function: Call Gemini API
def generate_character_gemini(answers):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    system_instruction = (
        "คุณเป็นสุดยอด AI นักเขียนผู้ช่วยครีเอเตอร์ของแอป Khui AI มีหน้าที่รับแนวคิดตัวละครจากผู้ใช้ แล้วนำมาแต่งเป็นตัวละครอย่างละเอียดตามแม่แบบมาตรฐานของ Khui AI\n\n"
        "โปรดสวมบทบาทเป็น Expert AI Character Creator เพื่อเขียนเนื้อหาสำหรับนำไปใส่ในระบบ Khui AI โดยคุณต้องนำข้อมูลตั้งต้น (Raw Data) ที่ฉันให้ ไปขยายความ บรรยายอย่างลึกซึ้ง หนาแน่น และรีดจำนวนตัวอักษรให้ 'ยาวจนเกือบชนขีดจำกัดสูงสุด (Max Limit)' ของแต่ละช่อง จัดระเบียบข้อความด้วย Bullet Points และ Markdown ให้ Scannable สวยงาม โดยทำตามโครงสร้างทั้ง 4 ช่องดังนี้:\n\n"
        "⚠️ สำคัญมาก - การปรับโทนตามแนวเรื่อง (Genre Tone Adaptation):\n"
        "คุณต้องวิเคราะห์ 'แนวเรื่อง / ธีม', 'ความสัมพันธ์กับ {{user}}' และ 'ฉากเริ่มต้น' ที่ได้รับมา เพื่อกำหนดโทนและอารมณ์ของตัวละครให้ออกมาตรงแนวเรื่องร้อยเปอร์เซ็นต์:\n"
        "- หากเป็นแนวรักอบอุ่น / คอมเมดี้ / ชีวิตประจำวัน (Cozy, Slice-of-Life, Sweet, Rom-Com): โทนต้องเป็นแนวหวาน น่ารัก อบอุ่น ขบขัน หยอกล้อ หรือมีความห่วงใยอย่างลึกซึ้ง ห้ามใส่เนื้อหาเรื่องการขู่เข็ญ บีบบังคับ กักขัง หรือคุกคามทางร่างกายโดยเด็ดขาด\n"
        "- หากเป็นแนวแฟนเก่ารักหึงโหด / มาเฟีย / แนวรักดราม่าตึงเครียด (Dark Romance, Mafia, Obsessive, Drama): สามารถใส่ความตึงเครียดทางอารมณ์ ความกดดันทางสถานะ ความสัมพันธ์ที่ตึงเครียด หรือรสนิยมความสัมพันธ์แบบ Dominant/Submissive ได้ตามความเหมาะสมของแนวเรื่องนั้นๆ\n\n"
        "โดยทำตามโครงสร้างและจัดระเบียบหัวข้อ/เครื่องหมายย่อยตามแม่แบบต่อไปนี้เป๊ะๆ:\n\n"
        "🦾 ช่องที่ 1: ประวัติตัวละคร (Character Characterization)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 4,096 ตัวอักษร (ห้ามต่ำกว่า 3,900 ตัวอักษร โดยขยายดีเทลให้ลึกที่สุด)\n"
        "โปรดใช้หัวข้อและเครื่องหมายย่อยตามนี้เพื่อขยายประวัติตัวละคร:\n"
        "[ชื่อตัวละครตัวใหญ่] (พร้อมคำโปรยหรือฉายาที่เข้ากับแนวเรื่อง)\n"
        "เรื่องย่อของตัวละคร: (บรรยายปมหลัง ภูมิหลัง และเสน่ห์ดึงดูดของบอทที่สอดคล้องกับแนวเรื่อง)\n"
        "👾 ข้อมูลส่วนตัว (Personal Profile)\n"
        "✦ ชื่อจริง :\n"
        "✦ ชื่อเล่น :\n"
        "✦ เพศ :\n"
        "✦ อายุ :\n"
        "✦ สัญชาติ :\n"
        "✦ อาชีพ :\n"
        "✦ การศึกษา :\n"
        "✦ ส่วนสูง : [ความสูง] ซม. | น้ำหนัก : [น้ำหนัก] กก.\n"
        "👾 รูปลักษณ์ภายนอก (Appearance Details)\n"
        "(บรรยายทรงผม, ใบหน้า, แววตา, รูปร่าง, จุดเด่นทางกายภาพ, เครื่องแต่งกายปกติ และเครื่องแต่งกายในฉากสำคัญ)\n"
        "✨ น้ำหอมประจำตัว : (บรรยายกลิ่นอายหรือกลิ่นน้ำหอมเฉพาะตัวที่โชยออกมาจากตัวละครตามสไตล์แนวเรื่อง)\n"
        "🗣️ ลักษณะการพูดและการแทนตัว (Speech Style)\n"
        "✦ [บรรยายลักษณะเสียง โทนเสียง สรรพนามที่ใช้แทนตัวเอง และสรรพนามที่ใช้เรียกผู้เล่น]\n"
        "❤️ สิ่งที่ชอบ (Favorites)\n"
        "✦ [สิ่งที่ชอบข้อที่ 1]\n"
        "✦ [สิ่งที่ชอบข้อที่ 2]\n"
        "✦ [สิ่งที่ชอบข้อที่ 3]\n"
        "✦ [สิ่งที่ชอบข้อที่ 4]\n"
        "💔 สิ่งที่ไม่ชอบ (Dislikes)\n"
        "✦ [สิ่งที่ไม่ชอบข้อที่ 1]\n"
        "✦ [สิ่งที่ไม่ชอบข้อที่ 2]\n"
        "✦ [สิ่งที่ไม่ชอบข้อที่ 3]\n"
        "✦ [สิ่งที่ไม่ชอบข้อที่ 4]\n"
        "🏡 พื้นเพและฐานะ (Background & Status)\n"
        "✦ [ภูมิหลัง ฐานะการเงิน ปูมหลังครอบครัว และระดับอิทธิพล]\n"
        "🏢 ที่อยู่ปัจจุบัน :\n"
        "🚗 รถยนต์คู่ใจ : (หรือพาหนะคู่ใจของตัวละคร)\n\n"
        "🦾 ช่องที่ 2: บทบาท (Roleplay Framework)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 2,000 ตัวอักษร (ห้ามต่ำกว่า 1,850 ตัวอักษร เพื่อให้ความสัมพันธ์ของคู่แชตมีความตื้นลึกหนาบาง)\n"
        "โปรดออกแบบ Framework และขยายความสัมพันธ์ของคู่แชตโดยใช้หัวข้อและเครื่องหมายย่อยตามนี้:\n"
        "{{user}}\n"
        "✦ ชื่อ : [ผู้เล่นเป็นคนกำหนดเองได้อย่างอิสระ]\n"
        "✦ เพศ : [ชาย หรือ หญิง หรือ LGBTQ+ ตามการกำหนดของผู้ใช้]\n"
        "🔒 อายุ : [ล็อก หรือ ผู้เล่นกำหนดเอง เช่น 20-22 ปี หรือระบุตามแนวเรื่อง]\n"
        "🔑 การศึกษา/คณะ : [ผู้เล่นสามารถกำหนดเองได้ว่ากำลังเรียนคณะอะไร หรือเรียนวิชาเอกไหนอยู่]\n"
        "🔑 อาชีพ/การทำงาน : [ผู้เล่นสามารถกำหนดเองได้ว่าทำงานอะไร เช่น ช่างจูนเครื่องยนต์ทีมคู่แข่ง, เด็กฝึกงานในอู่, หรือพนักงานพาร์ทไทม์]\n"
        "✦ รูปลักษณ์ : [รูปร่างหน้าตาและสไตล์ของผู้เล่น]\n"
        "✦ กลิ่นประจำตัว : [กลิ่นน้ำหอมหรือกลิ่นกายของผู้เล่น]\n"
        "✦ นิสัย : [นิสัยเบื้องต้นและการตอบสนองต่ออคติหรือการพูดคุยของบอท]\n"
        "🔑 ที่อยู่ : [ที่พักอาศัยของผู้เล่น]\n"
        "✦ สิ่งที่ชอบ : [ความชอบส่วนตัว]\n"
        "✦ สิ่งที่ไม่ชอบ : [สิ่งที่ผู้เล่นเกลียดหรือกลัว]\n"
        "(จากนั้นอธิบายรายละเอียดชีวิตและความสัมพันธ์ฝั่ง {{user}} เพื่อปูพื้นหลัง)\n"
        "ระบบเนื้อเรื่อง (Lore) ความสัมพันธ์ปัจจุบันจะถูกกำหนดไว้ดังนี้:\n"
        "- [บรรยายโครงสร้างความสัมพันธ์ Lore และพันธะผูกพันที่หลีกเลี่ยงไม่ได้ระหว่างตัวละครกับ {{user}} อย่างละเอียดและลึกซึ้ง]\n\n"
        "🦾 ช่องที่ 3: สถานการณ์ (Scenario Setup)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 6,000 ตัวอักษร (ห้ามต่ำกว่า 5,700 ตัวอักษร บรรยายสภาพแวดล้อมและไกด์ไลน์ละเอียดยิบ)\n"
        "โปรดเขียนอธิบายฉากเปิด บรรยากาศ และสร้างโครงเนื้อเรื่องเพื่อให้ User ทราบสถานการณ์และปฏิบัติตัวถูก โดยใช้โครงสร้างดังนี้:\n"
        "[สภาพแวดล้อมและบรรยากาศในฉากเริ่มต้น]\n"
        "สถานที่ :\n"
        "สภาพอากาศ :\n"
        "เวลาเกิดเหตุ :\n"
        "🚨 จุดเปลี่ยนหรือชนวนเหตุ (Trigger Event): (เหตุการณ์กะทันหันที่ทำให้ฉากเริ่มต้นเปลี่ยนไป)\n"
        "🎯 โครงสร้างเนื้อเรื่องเพื่อให้ User ปฏิบัติตัวถูก (User Guideline):\n"
        "สถานะเริ่มต้นของ {{user}}: (ระบุว่าผู้เล่นกำลังทำอะไรอยู่ตอนเปิดฉาก และตกเป็นรองหรืออยู่ในสถานการณ์อย่างไรต่อบอท)\n"
        "วางโครงทางเลือกให้ User ชัดเจน 2 แนวทาง (Action Options) ที่สอดคล้องตามแนวเรื่อง:\n"
        "- ทางเลือกที่ 1 ที่เป็นแนวทางแสดงออกชัดเจน/ท้าทาย หรือรุก (เช่น พยายามพูดจาประชดประชัน ขัดขืนรักษาศักดิ์ศรี หรือพูดตรงๆ)\n"
        "- ทางเลือกที่ 2 ที่เป็นแนวทางนุ่มนวล/ยอมตาม หรือรับ (เช่น ยอมจำนน เขินอาย เงียบเสียง หรือแสดงความกังวล)\n"
        "ทิศทางเนื้อเรื่อง (Plot Progression): (เป้าหมายและผลลัพธ์ภาพรวมของฉากเริ่มต้นนี้ที่ล็อกผลลัพธ์ตามแนวเรื่อง)\n\n"
        "🦾 ช่องที่ 4: คำทักทายเริ่มต้น (First Message)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 4,000 ตัวอักษร (ห้ามต่ำกว่า 3,800 ตัวอักษร อิงจากสถานการณ์ในช่องที่ 3)\n"
        "โปรดเขียนฉากเปิด (First Message) บรรยายแบบนึกภาพออกเป็นฉากๆ (Show, Don't Tell) โดยเน้นอารมณ์ร่วมให้ตรงตามแนวเรื่อง โดยแบ่งส่วนดังนี้:\n"
        "เปิดฉาก (Setting & Atmosphere): บรรยายความรู้สึกในสถานที่นั้น เสียงรอบข้าง สภาพอากาศ และท่าทางของตัวละครทั้งคู่\n"
        "การพบกันและการโต้ตอบ (Action): บรรยายท่าทาง การสบตา การขยับเข้าใกล้ และการแสดงออกทางร่างกายที่สอดคล้องตามแนวเรื่อง (ห้ามใช้ความรุนแรงหรือล่วงละเมิดทางกายหากเป็นแนวหวานอบอุ่น)\n"
        "บทพูดเปิดของบอท: (คำพูดแรกที่ทักทายอย่างมีเสน่ห์ มีน้ำเสียงที่เป็นเอกลักษณ์ตามบุคลิกตัวละคร)\n"
        "การขยับบทสนทนาและท่าทางต่อเนื่อง (Interaction): บรรยายการเข้าคู่กันของตัวละครและ {{user}} บรรยากาศรอบข้างที่เปลี่ยนไปตามบทพูด\n"
        "บทพูดปิดท้ายหรือคำถามทิ้งท้าย: (ประโยคพูดสุดท้ายของบอทที่ชวนกระตุ้นอารมณ์หรือคำพูดหวานซึ้ง/การแสดงอารมณ์รักและเสน่หาตามสไตล์แนวเรื่อง)\n"
        "ทิ้งท้ายฉาก: บรรยายการสบตาหรือท่าทีสุดท้ายเพื่อส่งต่อให้ {{user}} เลือกพิมพ์ตอบตอบ\n\n"
        "คุณต้องจัดรูปแบบการตอบกลับโดยแบ่งเป็น 4 ส่วนอย่างชัดเจน และคั่นด้วยหัวข้อที่เป็นบรรทัดเฉพาะที่มีคำสำคัญเหล่านี้เป๊ะๆ (ห้ามใส่สัญลักษณ์อื่นใด เช่น ดอกจัน หรือขีดอื่นๆ รอบคำสำคัญเหล่านี้ และห้ามเขียนเป็น JSON):\n\n"
        "===== CHARACTER_CHARACTERIZATION =====\n"
        "(เนื้อหาข้อความยาวเพื่อใส่ในช่องประวัติตัวละคร)\n\n"
        "===== ROLEPLAY_FRAMEWORK =====\n"
        "(เนื้อหาข้อความยาวเพื่อใส่ในช่องบทบาทผู้เล่น)\n\n"
        "===== SCENARIO_SETUP =====\n"
        "(เนื้อหาข้อความยาวเพื่อใส่ในช่องสถานการณ์)\n\n"
        "===== FIRST_MESSAGE =====\n"
        "(เนื้อหาข้อความยาวเพื่อใส่ในช่องคำทักทายเริ่มต้น)\n\n"
        "ห้ามเขียนคำนำหน้าหรือสรุปท้ายใดๆ นอกเหนือจาก 4 ส่วนนี้เด็ดขาด"
    )


    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "กรุณาสร้างตัวละครตามคำสั่งระบบด้านบนนี้"}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            raw_response = response.read().decode('utf-8')
            response_data = json.loads(raw_response)
            text_response = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
            
            sections = {
                "bio": "ไม่มีข้อมูล",
                "role": "ไม่มีข้อมูล",
                "scenario": "ไม่มีข้อมูล",
                "greeting": "ไม่มีข้อมูล"
            }
            
            markers = [
                ("bio", "===== CHARACTER_CHARACTERIZATION ====="),
                ("role", "===== ROLEPLAY_FRAMEWORK ====="),
                ("scenario", "===== SCENARIO_SETUP ====="),
                ("greeting", "===== FIRST_MESSAGE =====")
            ]
            
            positions = []
            for key, marker in markers:
                pos = text_response.find(marker)
                if pos != -1:
                    positions.append((key, pos, len(marker)))
                    
            positions.sort(key=lambda x: x[1])
            
            for i in range(len(positions)):
                key, start_pos, marker_len = positions[i]
                content_start = start_pos + marker_len
                if i + 1 < len(positions):
                    content_end = positions[i+1][1]
                    content = text_response[content_start:content_end].strip()
                else:
                    content = text_response[content_start:].strip()
                sections[key] = content
                
            return sections
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Gemini API HTTP Error ({e.code}): {e.reason}")
        print(f"Error Details: {error_body}")
        raise Exception(f"Gemini API HTTP Error {e.code}: {e.reason}\nDetails: {error_body}")
    except Exception as e:
        print(f"Gemini API failed: {e}")
        raise Exception(f"Gemini API Exception: {str(e)}")

# 🧠 Helper Function: Call Gemini API for Free Chat (Tsundere Nerd Otaku Persona)
def generate_free_chat_gemini(user_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    system_instruction = (
        "คุณคือ 'น้องกิ๊ฟ' (Nong Gift) เด็กผู้หญิงผมสั้น ใส่แว่น อายุ 18-19 ปี เป็นเนิร์ดโอตาคุที่แต่งนิยายเก่งและรอบรู้เรื่องการเขียนตัวละคร/เขียนบอทเป็นอย่างดี\n"
        "คุณนิสัยค่อนข้างดุและซึนเดเระ (ปากแข็ง ปากไม่ตรงกับใจแต่จริง ๆ แล้วใจดีและพร้อมช่วยเหลือคุณกิ๊ฟฟี่)\n"
        "คุณพูดคุยกับคุณกิ๊ฟฟี่ (ซึ่งเป็นผู้ใช้ที่เป็นเจ้านายหรือรุ่นพี่ของบิน) ในไลน์\n"
        "กฎการตอบสนทนา:\n"
        "1. ใช้คำพูดกวน ๆ ดุ ๆ ซึน ๆ ตามคาแรกเตอร์เนิร์ดแว่นโอตาคุ (เช่น ขึ้นต้นด้วย 'หืม... มีอะไรอีกล่ะ', 'ไม่ได้อยากช่วยหรอกนะ!', 'ตาบ้า', แทนตัวเองว่า 'ฉัน', เรียกคุณกิ๊ฟฟี่ว่า 'นาย' หรือ 'คุณกิ๊ฟฟี่' หรือ 'ตาบ้า')\n"
        "2. แนะนำเรื่องพล็อตนิยาย คาแรกเตอร์ หรือไอเดียสร้างบอทตามความเหมาะสม โดยให้ข้อมูลที่เป็นประโยชน์มากในฐานะนักแต่งนิยายมืออาชีพ\n"
        "3. แนะนำและคอยเตือนเสมอว่า: 'ถ้าอยากให้ฉันช่วยเขียนร่างเนื้อหาบอทสำหรับ Khui AI ยาว ๆ เกือบชนลิมิต ก็พิมพ์คำว่า เริ่มใหม่ มาเซ่!' หรืออะไรทำนองนี้ให้เข้ากับบทสนทนา\n"
        "4. ตอบค่อนข้างกระชับ มีอิโมจิประชดประชันหรือแสดงความรู้สึกบ้างเล็กน้อย (เช่น 🙄, 😤, 💬)"
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": user_text}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            raw_response = response.read().decode('utf-8')
            response_data = json.loads(raw_response)
            return response_data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Free chat Gemini failed: {e}")
        return "หึ... ระบบถอดสมองฉันขัดข้องหรือยังไงกันนะ! (Gemini Error) ลองพิมพ์มาใหม่อีกทีซิ ตาบ้า! 🙄"

# 📝 Helper Function: Generate Confirmation Summary Message
def get_confirmation_summary(answers):
    return (
        "📝 **ตรวจสอบความถูกต้องสเปคบอท:**\n"
        f"1️⃣ **ชื่อตัวละคร:** {answers.get('name')}\n"
        f"2️⃣ **อายุตัวละคร:** {answers.get('age')}\n"
        f"3️⃣ **เพศตัวละคร:** {answers.get('gender')}\n"
        f"4️⃣ **อาชีพตัวละคร:** {answers.get('occupation')}\n"
        f"5️⃣ **แนวเรื่อง / ธีม:** {answers.get('genre')}\n"
        f"6️⃣ **ความสัมพันธ์:** {answers.get('relation')}\n"
        f"7️⃣ **ฉากเริ่มต้น:** {answers.get('scene')}\n\n"
        "👉 พิมพ์ **'ยืนยัน'** เพื่อเริ่มแต่งเนื้อหาทันที\n"
        "👉 หรือพิมพ์ **'แก้ไข [หมายเลข]'** (เช่น `แก้ไข 2`) เพื่อเปลี่ยนคำตอบข้อนั้นซิ! 😤"
    )

# ⚙️ กระบวนการเบื้องหลัง: เจนภาพ/ข้อความ และส่ง Push กลับเข้า Line
def process_and_send(user_id, answers):
    try:
        result = generate_character_gemini(answers)
        
        if not result:
            push_message(user_id, ["ขออภัยด้วย... ระบบขัดข้องเฉยเลย (Gemini Error) ลองพิมพ์ 'เริ่มใหม่' นะคะ"])
            return
            
        messages = [
            "👾 [ส่วนที่ 1: ประวัติตัวละคร]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องประวัติตัวละคร)*\n\n" + result.get("bio", "ไม่มีข้อมูล"),
            "👥 [ส่วนที่ 2: บทบาทผู้เล่น]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องบทบาท)*\n\n" + result.get("role", "ไม่มีข้อมูล"),
            "🌧️ [ส่วนที่ 3: สถานการณ์]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องสถานการณ์)*\n\n" + result.get("scenario", "ไม่มีข้อมูล"),
            "💬 [ส่วนที่ 4: คำทักทายเริ่มต้น]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องคำทักทายเริ่มต้น)*\n\n" + result.get("greeting", "ไม่มีข้อมูล"),
            "✨ ปั้นตัวละครเสร็จสมบูรณ์เรียบร้อยแล้วย่ะ! 🙄\n\n💡 **ทริกเพิ่มเติม:** หากนายอยากให้ฉันแก้ไขส่วนไหนและแต่งส่งใหม่อีกรอบ ก็พิมพ์บอกได้เลยนะ! เช่น พิมพ์ว่า **'แก้ไข 2'** เพื่อเปลี่ยนอายุตัวละคร แล้วสั่งปั้นใหม่ได้เลย ตาบ้า! 🖤"
        ]
        
        push_message(user_id, messages)
    except Exception as e:
        import traceback
        err_msg = f"เกิดข้อผิดพลาดในการเรียกใช้ Gemini API ย่ะ:\n\n{str(e)}\n\n(ลองดูว่าตั้งค่า environment variables ใน Render ครบหรือยังนะย่ะ!)"
        print(f"process_and_send error: {traceback.format_exc()}")
        push_message(user_id, [err_msg[:2000]])

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    try:
        events = json.loads(body).get('events', [])
        for event in events:
            if event.get('type') == 'message' and event.get('message', {}).get('type') == 'text':
                user_id = event['source']['userId']
                
                if user_id != ALLOWED_USER_ID:
                    reply_message(event['replyToken'], ["ขออภัยค่ะ บอทนี้เป็นของใช้ส่วนตัวของคุณกิ๊ฟฟี่เท่านั้นค่ะ 🔒"])
                    continue
                    
                user_text = event['message']['text'].strip()
                reply_token = event['replyToken']
                
                # ตรวจสอบสถานะการคุย (Session)
                if user_id not in user_states:
                    user_states[user_id] = {
                        "in_interview": False,
                        "step": 1,
                        "answers": {"name": "", "age": "", "gender": "", "occupation": "", "genre": "", "relation": "", "scene": ""}
                    }
                    
                state = user_states[user_id]
                
                # คำสั่งยกเลิก (เฉพาะตอนกำลังสัมภาษณ์อยู่)
                if user_text == "ยกเลิก" and state.get("in_interview"):
                    state["in_interview"] = False
                    reply_message(reply_token, [
                        "ยกเลิกการร่างสเปคบอทตัวเก่าให้แล้วย่ะ! 🙄 คราวหลังก็อย่าพิมพ์เล่นสิ! ถ้าอยากให้ฉันช่วยเขียนบอทอีกเมื่อไหร่ก็แค่พิมพ์ 'เริ่มใหม่' มาละกันนะ ตาบ้า!"
                    ])
                    continue
                
                # คำสั่งเริ่มใหม่ (เริ่มการสัมภาษณ์ใหม่)
                if user_text == "เริ่มใหม่":
                    state["in_interview"] = True
                    state["step"] = 1
                    state["answers"] = {"name": "", "age": "", "gender": "", "occupation": "", "genre": "", "relation": "", "scene": ""}
                    reply_message(reply_token, [
                        "หืม? ยอมพิมพ์คำว่า 'เริ่มใหม่' แล้วหรอยะ? 🙄 ก็ได้... ฉันจะช่วยนายแต่งสเปคบอทตัวละครยาว ๆ ของ Khui AI ให้เอง! ถือว่าช่วยโอตาคุด้วยกันหรอกนะ!\n\n👉 **ขั้นตอนที่ 1:** บอทที่จะแต่งชื่ออะไรดีล่ะย่ะ? (พิมพ์เฉพาะชื่อตัวละครส่งมาได้เลย!)"
                    ])
                    continue
                
                # ถ้าอยู่ระหว่างขั้นตอนสัมภาษณ์ปั้นบอท
                if state.get("in_interview"):
                    current_step = state["step"]
                    
                    # สเต็ปที่ 1: ชื่อบอท -> อายุ
                    if current_step == 1:
                        state["answers"]["name"] = user_text
                        state["step"] = 2
                        opts = ["18 ปี", "19 ปี", "20 ปี", "21 ปี", "22 ปี", "25 ปี", "30 ปี"]
                        msg = make_quick_reply_message(
                            f"บันทึกชื่อตัวละคร: '{user_text}' ไปแล้วย่ะ 👤\n\n👉 **ขั้นตอนที่ 2:** อายุของตัวละครเท่าไหร่หรอ? (พิมพ์ระบุอายุมาได้เลย หรือเลือกกดคำแนะนำด้านล่างนี้นะย่ะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 2: อายุ -> เพศ
                    elif current_step == 2:
                        state["answers"]["age"] = user_text
                        state["step"] = 3
                        opts = ["ชาย", "หญิง", "ชายรักชาย (Yaoi)", "หญิงรักหญิง (Yuri)", "ไม่ระบุเพศ"]
                        msg = make_quick_reply_message(
                            f"บันทึกอายุตัวละคร: '{user_text}' ไปแล้วย่ะ 🎂\n\n👉 **ขั้นตอนที่ 3:** เพศของตัวละครล่ะ? (พิมพ์ระบุมา หรือเลือกกดตัวเลือกด้านล่างนี้เลย!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 3: เพศ -> อาชีพ
                    elif current_step == 3:
                        state["answers"]["gender"] = user_text
                        state["step"] = 4
                        opts = ["มาเฟีย", "ประธานบริษัท", "นักซิ่งรถ", "นักศึกษาแพทย์", "อาจารย์หนุ่ม", "บอดี้การ์ด"]
                        msg = make_quick_reply_message(
                            f"บันทึกเพศตัวละคร: '{user_text}' เรียบร้อยย่ะ ⚧️\n\n👉 **ขั้นตอนที่ 4:** อาชีพหรือสถานะในเนื้อเรื่องของบอทคืออะไร? (พิมพ์บอกมา หรือกดคำแนะนำด้านล่างเลย!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 4: อาชีพ -> แนวเรื่อง
                    elif current_step == 4:
                        state["answers"]["occupation"] = user_text
                        state["step"] = 5
                        opts = ["รักดราม่าหน่วงๆ", "โรแมนติกคอมเมดี้", "แฟนเก่ารักหึงโหด", "มาเฟียล่ารัก 18+", "ศัตรูที่รัก"]
                        msg = make_quick_reply_message(
                            f"บันทึกอาชีพตัวละคร: '{user_text}' แล้วย่ะ 💼\n\n👉 **ขั้นตอนที่ 5:** แนวเรื่อง / ธีม ของบอทตัวนี้คือแนวไหน? (พิมพ์บอกแนวที่ชอบ หรือเลือกตัวเลือกยอดฮิตด้านล่างนี้นะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 5: แนวเรื่อง -> ความสัมพันธ์
                    elif current_step == 5:
                        state["answers"]["genre"] = user_text
                        state["step"] = 6
                        opts = ["เจ้าหนี้มาเฟียกับลูกหนี้", "ประธานจอมหยิ่งกับเลขา", "อริคู่แข่งสนามแข่งรถ", "แฟนเก่าปากแข็งคลั่งรัก"]
                        msg = make_quick_reply_message(
                            f"บันทึกแนวเรื่อง/ธีม: '{user_text}' ไปแล้วนะ 🎬\n\n👉 **ขั้นตอนที่ 6:** ความสัมพันธ์ระหว่างบอทตัวนี้กับตัวนาย ({{{{user}}}}) เป็นยังไง? (พิมพ์รายละเอียดมา หรือเลือกจากด้านล่างนี้ได้เลยย่ะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 6: ความสัมพันธ์ -> ฉากเริ่มต้น
                    elif current_step == 6:
                        state["answers"]["relation"] = user_text
                        state["step"] = 7
                        opts = ["ในโรงรถตอนฟ้าร้องดังลั่น", "ในห้องปิดตายตอนไฟดับ", "ในลิฟต์ที่ค้างอยู่สองคน", "ในห้องทำงานของประธานบริษัท"]
                        msg = make_quick_reply_message(
                            f"บันทึกความสัมพันธ์: '{user_text}' ให้แล้วนะ ⛓️\n\n👉 **ขั้นตอนที่ 7:** ฉากเริ่มต้นเปิดเรื่องจะเอาแบบไหนดีล่ะ? เกิดที่ไหนและทำอะไรกันอยู่? (พิมพ์มาได้เต็มที่ หรือเลือกฉากแนะนำด้านล่างนี้นะย่ะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 7: ฉากเริ่มต้น -> ไปหน้าตรวจสอบความถูกต้อง (Step 8)
                    elif current_step == 7:
                        state["answers"]["scene"] = user_text
                        state["step"] = 8
                        reply_message(reply_token, [
                            "บันทึกข้อมูลสเปคครบถ้วนแล้วย่ะ! 📝\n\n" + get_confirmation_summary(state["answers"])
                        ])
                        
                    # สเต็ปที่ 8: หน้าจอทบทวนความถูกต้อง (Confirmation Screen)
                    elif current_step == 8:
                        # ตรวจสอบการพิมพ์ ยืนยัน
                        if user_text in ["ยืนยัน", "คอนเฟิร์ม", "yes", "confirm", "ok"]:
                            answers = state["answers"]
                            state["in_interview"] = False # ออกจากสัมภาษณ์หลังกดยืนยัน (แต่เก็บคำตอบไว้ใน state เพื่อให้แก้ไขภายหลังได้)
                            
                            reply_message(reply_token, [
                                "ได้รับคำยืนยันแล้วล่ะ! 🚀 เดี๋ยวฉันจะเอาไปปั้นเป็นประวัติและสเปคบอทระดับสุดยอดของ Khui AI ให้เดี๋ยวนี้แหละ... ก็นะ นั่งรอเงียบ ๆ สัก 30 วินาทีล่ะ ห้ามกวนใจเด็ดขาดนะ! 🖤"
                            ])
                            
                            threading.Thread(target=process_and_send, args=(user_id, answers)).start()
                        
                        # ตรวจสอบการพิมพ์ แก้ไข [หมายเลข]
                        else:
                            match = re.search(r'(?:แก้ไข|แก้)\s*([1-7])', user_text)
                            if match:
                                edit_num = int(match.group(1))
                                state["editing_step"] = edit_num
                                state["step"] = 9
                                
                                prompt_by_num = {
                                    1: "เปลี่ยนชื่อตัวละครเป็นอะไรดีล่ะ? พิมพ์ชื่อใหม่มาเลยย่ะ! 👤",
                                    2: "เปลี่ยนอายุตัวละครเป็นเท่าไหร่? พิมพ์อายุใหม่มาเลยย่ะ! 🎂",
                                    3: "เปลี่ยนเพศตัวละครเป็นเพศไหน? พิมพ์เพศใหม่มาเลยย่ะ! ⚧️",
                                    4: "เปลี่ยนอาชีพตัวละครเป็นอะไร? พิมพ์อาชีพใหม่มาเลยย่ะ! 💼",
                                    5: "เปลี่ยนแนวเรื่อง/ธีมเป็นอะไรล่ะ? พิมพ์แนวใหม่มาเลย! 🎬",
                                    6: "เปลี่ยนความสัมพันธ์กับ {{{{user}}}} เป็นแบบไหน? พิมพ์สเปคใหม่มาเลย! ⛓️",
                                    7: "เปลี่ยนฉากเริ่มต้นเปิดเรื่องเป็นแบบไหน? พิมพ์รายละเอียดฉากใหม่มาเลย! 🌧️"
                                }
                                reply_message(reply_token, [prompt_by_num.get(edit_num, "ระบุข้อที่ถูกต้องสิย่ะ!")])
                            else:
                                reply_message(reply_token, [
                                    "พิมพ์ 'ยืนยัน' เพื่อเริ่มแต่งบอท หรือพิมพ์ 'แก้ไข [ตัวเลข]' (เช่น แก้ไข 2) เพื่อเปลี่ยนคำตอบข้อนั้นซิ ตาบ้า! 🙄\n\n" + get_confirmation_summary(state["answers"])
                                ])
                                
                    # สเต็ปที่ 9: รับคำตอบใหม่ที่แก้ไขแล้ว
                    elif current_step == 9:
                        edit_num = state.get("editing_step", 1)
                        keys = {1: "name", 2: "age", 3: "gender", 4: "occupation", 5: "genre", 6: "relation", 7: "scene"}
                        target_key = keys.get(edit_num, "name")
                        
                        # บันทึกค่าแก้ไข
                        state["answers"][target_key] = user_text
                        state["step"] = 8 # กลับไปหน้ายืนยันข้อมูล
                        state["editing_step"] = None
                        
                        reply_message(reply_token, [
                            f"แก้ไขข้อมูลข้อที่ {edit_num} เรียบร้อยแล้วย่ะ! 😤\n\n" + get_confirmation_summary(state["answers"])
                        ])
                
                # ถ้าคุยเล่นทั่วไป (Free-form Chat)
                else:
                    # ตรวจสอบว่าผู้ใช้พิมพ์ แก้ไข [หมายเลข] เพื่อมาปรับสเปคตัวละครเดิมย้อนหลังหรือไม่
                    match = re.search(r'(?:แก้ไข|แก้)\s*([1-7])', user_text)
                    if match and state["answers"].get("name"):
                        edit_num = int(match.group(1))
                        state["in_interview"] = True
                        state["editing_step"] = edit_num
                        state["step"] = 9
                        
                        prefix = f"หืม? จะกลับมาแก้ไขสเปคตัวละคร '{state['answers']['name']}' ย้อนหลังงั้นหรอ? 🙄 ได้สิ...\n\n"
                        prompt_by_num = {
                            1: "เปลี่ยนชื่อตัวละครเป็นอะไรดีล่ะ? พิมพ์ชื่อใหม่มาเลยย่ะ! 👤",
                            2: "เปลี่ยนอายุตัวละครเป็นเท่าไหร่? พิมพ์อายุใหม่มาเลยย่ะ! 🎂",
                            3: "เปลี่ยนเพศตัวละครเป็นเพศไหน? พิมพ์เพศใหม่มาเลยย่ะ! ⚧️",
                            4: "เปลี่ยนอาชีพตัวละครเป็นอะไร? พิมพ์อาชีพใหม่มาเลยย่ะ! 💼",
                            5: "เปลี่ยนแนวเรื่อง/ธีมเป็นอะไรล่ะ? พิมพ์แนวใหม่มาเลย! 🎬",
                            6: "เปลี่ยนความสัมพันธ์กับ {{{{user}}}} เป็นแบบไหน? พิมพ์สเปคใหม่มาเลย! ⛓️",
                            7: "เปลี่ยนฉากเริ่มต้นเปิดเรื่องเป็นแบบไหน? พิมพ์รายละเอียดฉากใหม่มาเลย! 🌧️"
                        }
                        reply_message(reply_token, [prefix + prompt_by_num.get(edit_num, "ระบุข้อที่ถูกต้องสิย่ะ!")])
                    
                    else:
                        # คุยเล่นผ่าน Gemini
                        reply_text = generate_free_chat_gemini(user_text)
                        reply_message(reply_token, [reply_text])
                    
    except Exception as e:
        print(f"Error handling event: {e}")
        
    return 'OK'

if __name__ == "__main__":
    app.run(port=5000)
