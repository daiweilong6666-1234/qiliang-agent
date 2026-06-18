# ============================================================
# 【报错原因】原来的代码全部是注释(#开头)，Python解释器读到的是空文件，没有任何可执行语句
# 以下为完整的 FastAPI CRUD 代码，运行前先执行: pip install fastapi uvicorn
# ============================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn

# 【报错原因】如果没有创建 app 实例，后续 @app.get() / @app.post() 装饰器找不到 app 变量，会报 NameError
app = FastAPI(title="学生管理系统 API")

# === 数据模型 ===
# 【报错原因】FastAPI 必须用 Pydantic BaseModel 定义数据结构
# 如果直接传普通 dict，FastAPI 无法自动校验字段类型，前端传错数据不会报错
class Student(BaseModel):
    id: int = Field(description="学生ID")
    name: str = Field(min_length=1, max_length=50)
    age: int = Field(ge=1, le=150)
    grade: str = Field(default="一年级")

class StudentUpdate(BaseModel):
    # 【报错原因】更新操作如果用同一个 Student 模型，所有字段都会变成必填，无法实现部分更新
    # Optional 让这些字段可选，只更新用户传了的字段
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    age: Optional[int] = Field(None, ge=1, le=150)
    grade: Optional[str] = None

# === 模拟数据库 ===
# 【报错原因】没有数据存储的话，CRUD 操作无法验证效果，用内存字典模拟即可学习测试
fake_db: dict[int, Student] = {}

# === 查询学生 ===
@app.get("/selectstudent/")
async def select_student(id: int):
    """根据ID查询学生: http://127.0.0.1:8000/selectstudent/?id=1"""
    student = fake_db.get(id)
    if student is None:
        # 【报错原因】找不到资源必须返回 404，如果 return None 前端无法判断是"没数据"还是"接口挂了"
        raise HTTPException(status_code=404, detail=f"学生 ID={id} 不存在")
    return student

@app.get("/selectstudent/all")
async def select_all_students():
    """查询全部学生"""
    return list(fake_db.values())

# === 添加学生 ===
@app.post("/addstudent/")
async def add_student(student: Student):
    """添加学生: POST 请求体 {"id":1,"name":"张三","age":20,"grade":"二年级"}"""
    if student.id in fake_db:
        # 【报错原因】不检查重复直接覆盖会导致数据丢失，应该拒绝并提示用户
        raise HTTPException(status_code=400, detail=f"学生 ID={student.id} 已存在")
    fake_db[student.id] = student
    return {"message": "添加成功", "student": student}

# === 更新学生 ===
@app.put("/updatestudent/")
async def update_student(id: int, student_update: StudentUpdate):
    """更新学生: PUT 请求体 {"name":"张三丰","age":21}"""
    existing = fake_db.get(id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"学生 ID={id} 不存在")
    # 【报错原因】model_dump(exclude_unset=True) 只提取用户实际传了的字段
    # 如果不用这个，None 值会覆盖原有数据，导致字段被意外清空
    update_data = student_update.model_dump(exclude_unset=True)
    updated_student = existing.model_copy(update=update_data)
    fake_db[id] = updated_student
    return {"message": "更新成功", "student": updated_student}

# === 删除学生 ===
@app.delete("/deletestudent/")
async def delete_student(id: int):
    """删除学生: http://127.0.0.1:8000/deletestudent/?id=1"""
    student = fake_db.pop(id, None)
    if student is None:
        
        raise HTTPException(status_code=404, detail=f"学生 ID={id} 不存在")
    return {"message": "删除成功", "student": student}

# === 启动入口 ===
# 【报错原因】原来的文件没有 if __name__ == "__main__" 启动入口
# Python 直接执行文件时不会自动启动 uvicorn 服务器，必须显式调用 uvicorn.run()
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
