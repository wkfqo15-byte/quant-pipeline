from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
import secrets
import string
import os

app = FastAPI()

rooms_db = {}
UPLOAD_DIR = "uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.get("/create-room")
def create_room():
    alphabet = string.ascii_letters + string.digits
    secure_code = ''.join(secrets.choice(alphabet) for _ in range(6))
    rooms_db[secure_code] = {"status": "active", "files": []}
    return {"status": "success", "room_code": secure_code, "message": f"방이 생성되었습니다. (입장 코드: {secure_code})"}

@app.get("/join-room/{room_code}")
def join_room(room_code: str):
    if room_code in rooms_db:
        # 🌟 수정됨: 방에 입장할 때, 방에 저장된 파일 '목록'도 함께 보내줍니다.
        return {
            "status": "success", 
            "message": f"{room_code} 방에 성공적으로 입장했습니다!",
            "files": rooms_db[room_code]["files"]
        }
    else:
        return {"status": "error", "message": "존재하지 않거나 이미 삭제된 방입니다."}

@app.post("/upload/{room_code}")
async def upload_file(room_code: str, file: UploadFile = File(...)):
    if room_code not in rooms_db:
        return {"status": "error", "message": "방을 찾을 수 없습니다."}
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    rooms_db[room_code]["files"].append(file.filename)
    
    return {"status": "success", "message": f"'{file.filename}' 파일이 서버에 저장되었습니다!"}

# 🌟 새로 추가됨: 서버에 저장된 파일을 다운로드하는 주소
@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    # 폴더에 파일이 진짜 있는지 확인하고 돌려줍니다.
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename) # filename을 지정하면 브라우저가 자동 다운로드합니다.
    else:
        return {"status": "error", "message": "파일을 찾을 수 없습니다."}