from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
import models, schemas, database
import csv
import io

models.Base.metadata.create_all(bind=database.engine)
app = FastAPI(title="GDG Premium API - Ultimate Edition")

SECRET_KEY = "super-secret-gdg-key-2026"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- HELPER FUNCTIONS ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_premium(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    # OPTIONAL REQUIREMENT: 30-Day Expiration Logic
    if current_user.is_premium and current_user.subscription_expires_at:
        if datetime.now(timezone.utc) > current_user.subscription_expires_at:
            current_user.is_premium = False
            db.commit()
            raise HTTPException(status_code=403, detail="Your premium subscription has expired.")

    if not current_user.is_premium:
        raise HTTPException(status_code=403, detail="Premium subscription required")
    
    log = models.AccessLog(user_id=current_user.id, endpoint=str(request.url.path), ip_address=request.client.host)
    db.add(log)
    db.commit()
    return current_user

def require_admin(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# --- ENDPOINTS ---
@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pw = pwd_context.hash(user.password)
    
    # Secret Trick: If the username is "admin", make them an admin automatically!
    is_admin_user = True if user.username.lower() == "admin" else False
    
    new_user = models.User(username=user.username, hashed_password=hashed_pw, is_admin=is_admin_user)
    db.add(new_user)
    db.commit()
    return {"username": new_user.username, "is_admin": new_user.is_admin}

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/upgrade")
def upgrade_subscription(current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    current_user.is_premium = True
    # Sets expiration to exactly 30 days from now!
    current_user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.commit()
    return {"message": f"Payment successful. Premium access valid for 30 days!"}

@app.get("/content/premium")
def get_premium_content(current_user: models.User = Depends(require_premium)):
    return {"content": f"Welcome to the VIP lounge, {current_user.username}!"}

# --- OPTIONAL ADMIN ENDPOINTS ---
@app.get("/admin/logs")
def view_access_logs(admin_user: models.User = Depends(require_admin), db: Session = Depends(database.get_db)):
    logs = db.query(models.AccessLog).all()
    return {"total_logs": len(logs), "data": logs}

@app.get("/admin/reports/csv")
def generate_csv_report(admin_user: models.User = Depends(require_admin), db: Session = Depends(database.get_db)):
    logs = db.query(models.AccessLog).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Log ID", "User ID", "Endpoint Accessed", "IP Address", "Timestamp"])
    
    for log in logs:
        writer.writerow([log.id, log.user_id, log.endpoint, log.ip_address, log.accessed_at])
    
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=monthly_usage_report.csv"})