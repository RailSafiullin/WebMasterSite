import logging
import re
from fastapi import Form
from typing import Dict
from datetime import datetime
from alembic import command
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.auth_config import current_user
from api.auth.models import GroupUserAssociation, User
from api.config.models import Config, GroupConfigAssociation, List, ListURI, Role, Group, UserQueryCount
from api.config.utils import get_config_info
from config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
from db.session import get_db_general
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="static")

from fastapi_users.password import PasswordHelper

from alembic.config import Config as AlembicConfig

import asyncpg

router = APIRouter()

ROLES_PERMISSIONS = {
    "User": {},
    "Administrator": {"User"},
    "Superuser": {"User", "Administrator", "Superuser"},
}


@router.post('/add-config')
async def add_config(request: Request,
                     formData: dict,
                     session: AsyncSession = Depends(get_db_general),
                     user: User = Depends(current_user)):
    name, database_name, access_token, user_id, host_id = (formData["name"],
                                                           formData["database_name"],
                                                           formData["access_token"],
                                                           formData["user_id"],
                                                           formData["host_id"])

    config = Config(id_author=user.id, name=name,
                    database_name=database_name,
                    access_token=access_token,
                    user_id=user_id,
                    host_id=host_id)

    session.add(config)
    await session.commit()

    conn = await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database="postgres")
    try:
        await conn.execute(f'CREATE DATABASE "{database_name}"')
        print(f"CREATE DATABASE {database_name}: successfully")
    except asyncpg.exceptions.DuplicateDatabaseError:
        print(f"CREATE DATABASE {database_name}: database already exists")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await conn.close()

    # Применение миграций Alembic
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url",
                                f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{database_name}")
    command.upgrade(alembic_cfg, "head")

    return {"status": 200}


@router.post("/set-config")
async def set_config(request: Request,
                     config_name: dict,
                     session: AsyncSession = Depends(get_db_general),
                     user: User = Depends(current_user)):
    result = await get_config_info(session, config_name['config_name'], user.id)
    request.session["config"] = {
                                "config_id": result.id,
                                "database_name": result.database_name,
                                 "access_token": result.access_token,
                                 "user_id": result.user_id,
                                 "host_id": result.host_id,
                                }  
    
    return {"status": 200, "details": request.session}


@router.post("/set-group")
async def set_group(
        request: Request,
        group_name: Dict[str, str],
        session: AsyncSession = Depends(get_db_general),
        user: User = Depends(current_user)
):
    # Получение group_id по имени группы
    result = await session.execute(select(Group.id).where(Group.name == group_name["group_name"]))
    group_id = result.scalars().first()
    
    if group_id is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    
    # Получение первой конфигурации для группы
    config_association = (await session.execute(
        select(GroupConfigAssociation.config_id).where(GroupConfigAssociation.group_id == group_id).limit(1)
    )).scalars().first()

    config_record = (await session.execute(select(Config).where(Config.id == config_association))).scalars().first()

    print(config_record)
    
    # Установка значений конфигурации
    if config_record:
        request.session["group"] = {
            "group_id": group_id,
            "name": group_name["group_name"],
        }
        request.session["config"] = {
            "config_id": config_association,
            "database_name": config_record.database_name,
            "access_token": config_record.access_token,
            "user_id": config_record.user_id,
            "host_id": config_record.host_id,
        }
    else:
        # Если нет конфигурации для группы, можно установить значения по умолчанию
        request.session["group"] = {
            "group_id": group_id,
            "name": group_name["group_name"],
        }
        request.session["config"] = {
            "config_id": -1,
            "database_name": "",
            "access_token": "",
            "user_id": -1,
            "host_id": "",
        }
    
    print(request.session)
    return {
        "status": 200,
        "details": {
            "group": request.session["group"],
            "config": request.session["config"],
            "config_name": config_record.name
        }
    }

from api.auth.auth_config import PermissionRoleChecker, RoleChecker

@router.get("/roles")
async def get_roles(
        request: Request,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
        required: bool = Depends(RoleChecker(required_permissions={"Superuser"})),
) -> dict:
    query = select(Role).order_by(Role.id)
    result = (await session.execute(query)).scalars().all() 
    return templates.TemplateResponse("roles.html", 
                                    {"request": request, 
                                    "user": user,
                                    "roles": result,
                                    })
    #return {"roles": result}  # Возвращаем JSON объект с ключом "roles"

@router.post("/roles/add")
async def add_role(
        request: Request,
        formData: dict,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
        required: bool = Depends(RoleChecker(required_permissions={"Superuser"})
)):
    new_role = Role(name=formData['role_name'])
    session.add(new_role)
    await session.commit()
    await session.refresh(new_role)
    return {"status": "success", "new_role": new_role}

@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, session: AsyncSession = Depends(get_db_general)):
    query = select(Role).where(Role.id == role_id)
    result = await session.execute(query)
    role = result.scalars().first()

    if role:
        await session.delete(role)
        await session.commit()
        return {"status": 200, "message": "Role deleted successfully"}
    raise HTTPException(status_code=404, detail="Role not found")

@router.put("/roles/{role_id}/edit")
async def edit_role(role_id: int, request: Request, session: AsyncSession = Depends(get_db_general)):
    # Extracting JSON body data
    body = await request.json()
    edit_role_name = body.get("edit_role_name")

    # Query to get the role
    query = select(Role).where(Role.id == role_id)
    result = await session.execute(query)
    role = result.scalars().first()

    if role:
        role.name = edit_role_name  # Update role name
        await session.commit()
        return {"status": 200, "message": "Role updated successfully"}
    
    raise HTTPException(status_code=404, detail="Role not found")
@router.post("/roles/{role_id}/modules")
async def update_role_modules(role_id: int, request: Request, session: AsyncSession = Depends(get_db_general)):
    json_data = await request.json()
    query = select(Role).where(Role.id == role_id)
    result = await session.execute(query)
    role = result.scalars().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    for key, value in json_data.items():
        setattr(role, key, value) 

    '''
    # Можно обрабатывать пустые ключи на backend, отправляя только ключи со значением true, вместо отправки всех ключей 
    keys_of_role = list(filter(lambda item: item.startswith("access"), role.__dict__.keys()))
    for key_of_role in keys_of_role:
        if key_of_role not in json_data.keys():
            with open('data_output.txt', 'w', encoding='utf-8') as f: f.write(str(key_of_role + " = " + "off"))
            setattr(role, key_of_role, False)
    '''
    await session.commit()
    return {"message": "Role modules updated successfully"}


@router.get("/username")
async def get_usernames(
        request: Request,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
) -> dict:
    # Получаем роль текущего пользователя
    user_role = ((await session.execute(select(Role.name).where(Role.id == user.role))).fetchone())[0]

    # Получаем список ролей, которые текущий пользователь может видеть
    allowed_roles = ROLES_PERMISSIONS.get(user_role, set())

    # Получаем пользователей, у которых есть одна из разрешенных ролей
    query = select(User.username).join(Role).where(Role.name.in_(allowed_roles))
    result = (await session.execute(query)).scalars().all()  # Получаем все значения в виде списка строк

    return {"usernames": result}


@router.get("/config")
async def get_configs(
        request: Request,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
) -> dict:
    query = select(Config.name)
    result = (await session.execute(query)).scalars().all()  # Получаем все значения в виде списка строк
    return {"configs": result} 


@router.post("/add-user-to-group")
async def add_user_to_group(
        request: Request,
        formData: dict,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
):
    group_name, username = formData.values()

    user_role = ((await session.execute(select(Role.name).where(Role.id == user.role))).fetchone())[0]
    group = ((await session.execute(select(Group).where(Group.name == group_name))).fetchone())
    new_user, role = (await session.execute(
        select(User, Role.name)
        .join(Role, User.role == Role.id)
        .where(User.username == username)
    )).fetchone()

    if group is None and user is None:
        raise HTTPException(status_code=404, detail="Group and User do not exist.")
    elif role not in ROLES_PERMISSIONS[user_role]:
        raise HTTPException(status_code=403, detail="Вы не можете добавить пользователя с такими правами")
    elif group is None:
        raise HTTPException(status_code=404, detail="Group does not exist.")
    elif user is None:
        raise HTTPException(status_code=404, detail="User does not exist.")

    group = group[0]
    group.users.append(new_user)
    await session.commit()

    return {
        "status": "success",
        "message": f"{username} added to {group_name}"
    }


@router.post("/delete-user-from-group")
async def delete_user_from_group(
        request: Request,
        formData: dict,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
):
    group_name, username = formData.values()

    # Получение группы и пользователя из базы данных
    group = (await session.execute(select(Group).where(Group.name == group_name))).fetchone()
    user = (await session.execute(select(User).where(User.username == username))).fetchone()

    # Проверка на существование группы и пользователя
    if group is None and user is None:
        raise HTTPException(status_code=404, detail="Group and User do not exist.")
    elif group is None:
        raise HTTPException(status_code=404, detail="Group does not exist.")
    elif user is None:
        raise HTTPException(status_code=404, detail="User does not exist.")

    group, user = group[0], user[0]

    # Удаление пользователя из группы
    if user in group.users:

        await session.execute(
            delete(ListURI).where(
                ListURI.list_id.in_(
                    select(List.id).where(
                        and_(
                            List.author == user.id,
                            List.group == group.id
                        )
                    )
                )
            )
        )

        # Удаление записей из таблицы List
        await session.execute(
            delete(List).where(
                and_(
                    List.author == user.id,
                    List.group == group.id
                )
            )
        )
        
        group.users.remove(user)
        await session.commit()
        return {
            "status": "success",
            "message": f"{username} removed from {group_name}"
        }
    else:
        raise HTTPException(status_code=404, detail="User is not in the group.")


@router.put("/user/{id}")
async def edit_user(
    request: Request,
    id: int,
    formData: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    email, password, role, username, is_active, query_count = (
        formData.get('email'), 
        formData.get('password'),
        int(formData.get('role')), 
        formData.get('username'), 
        formData.get('is_active'), 
        int(formData.get('query_count')))
    user = (await session.execute(select(User).where(User.id == id))).scalars().first()
    user_query_count = (await session.execute(select(UserQueryCount).where(UserQueryCount.user_id == id))).scalars().first()


    if email:
        user.email = email
    if password:
        password_helper = PasswordHelper()
        user.hashed_password = password_helper.hash(password)
    if role:
        user.role = role
    if username:
        user.username = username
    user.is_active = is_active
    #if is_active:
    if not query_count:
        query_count = 0
    if user_query_count:
        user_query_count.query_count = query_count
    else:
        user_query_count = UserQueryCount(
            user_id=user.id,
            query_count=query_count, 
            last_update_date=datetime.now()
    )
    session.add(user_query_count)

    await session.commit()

    return {
        "status": 200,
        "message": f"Updated user with id: {id}",
    }


@router.delete("/user/{id}")
async def delete_user(
    request: Request,
    id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    user = (await session.execute(select(User).where(User.id == id))).scalars().first()

    await session.delete(user)

    await session.commit()

    return {
        "status": 200,
        "message": f"delete user with id: {id}",
    }


@router.get("/user_group/{user_id}")
async def get_users_group(
    user_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    print(user_id)
    # Получаем список групп для указанного user_id
    groups = await session.execute(
        select(GroupUserAssociation.group_id)
        .where(GroupUserAssociation.user_id == user_id)
    )
    group_ids = groups.scalars().all()

    # Получаем информацию о группах
    groups_info = await session.execute(
        select(Group).where(Group.id.in_(group_ids))
    )
    groups_data = groups_info.scalars().all()

    print([{"id": group.id, "name": group.name} for group in groups_data])

    return [{"id": group.id, "name": group.name} for group in groups_data]

@router.delete("/user_group/{user_id}/{group_id}")
async def delete_group_for_user(
    request: Request,
    user_id: int,
    group_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    group_obj = (await session.execute(select(
        GroupUserAssociation).where(
            and_(GroupUserAssociation.group_id == group_id, GroupUserAssociation.user_id == user_id)))).scalars().first()
    

    await session.delete(group_obj)

    await session.commit()

    return {
        "status": 200,
        "message": f"delete group ID:{group_id} for user ID: {user_id}"
    }


@router.post("/user_group/{user_id}/{group_id}")
async def add_group_for_user(
    request: Request,
    user_id: int,
    group_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    session.add(GroupUserAssociation(user_id = user_id, group_id=group_id))

    await session.commit()

    return {
        "status": 200,
        "message": f"add group ID: {group_id} for user ID: {user_id}"
    }



@router.post("/group")
async def add_group(
        request: Request,
        formData: dict,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
):
    print(formData)
    group_name = formData['name']
    configs = [int(elem) for elem in formData['configs']]

    res = (await session.execute(select(Group).where(Group.name == group_name))).scalar()

    if res:
        return {
            "status": "error",
            "message": "group already exists"
        }

    # Создание новой группы
    new_group = Group(name=group_name, id_author = user.id)

    # Добавление конфигураций
    configs_objects = []
    for config_id in configs:
        result = await session.execute(select(Config).filter_by(id=config_id))
        config = result.scalars().first()
        if config:
            configs_objects.append(config)
        else:
            raise HTTPException(status_code=404, detail=f"Config '{config_id}' not found")

    new_group.configs = configs_objects

    # Добавление новой группы в базу данных
    session.add(new_group)

    await session.commit()

    session.add(GroupUserAssociation(user_id=user.id, group_id=new_group.id))
    await session.commit()

    return {"status": "success", "group": new_group.id}



@router.delete("/group/{group_id}")
async def delete_group(
    request: Request,
    group_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    group_obj = (await session.execute(select(Group).where(Group.id == group_id))).scalar()

    await session.delete(group_obj)

    await session.commit()

    return {
        "status": 200,
        "message": f"delete group ID: {group_id}"
    }



@router.get("/group/{group_id}")
async def get_groups_config(
    request: Request,
    group_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    # Получаем список групп для указанного user_id
    configs = await session.execute(
        select(GroupConfigAssociation.config_id)
        .where(GroupConfigAssociation.group_id == group_id)
    )
    config_ids = configs.scalars().all()

    # Получаем информацию о группах
    configs_info = await session.execute(
        select(Config).where(Config.id.in_(config_ids))
    )
    configs_data = configs_info.scalars().all()

    print([{"id": group.id, "name": group.name} for group in configs_data])

    return [{"id": group.id, "name": group.name} for group in configs_data]


@router.delete("/group_config/{group_id}/{config_id}")
async def delete_config_from_group(
    request: Request,
    group_id: int,
    config_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    stmt = select(GroupConfigAssociation).where(
        and_(GroupConfigAssociation.group_id == group_id, GroupConfigAssociation.config_id == config_id))
    group_config_obj = (await session.execute(stmt)).scalar()

    await session.delete(group_config_obj)

    await session.commit()

    return {
        "status": 200,
        "message": f"delete config ID: {config_id} from group ID: {group_id}"
    }


@router.post("/group_config/{group_id}/{config_id}")
async def add_group_for_user(
    request: Request,
    group_id: int,
    config_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
):
    session.add(GroupConfigAssociation(group_id = group_id, config_id=config_id))

    await session.commit()

    return {
        "status": 200,
        "message": f"add config ID: {config_id} for group ID: {group_id}"
    }

# ----------------
@router.put("/config/{id}")
async def edit_config(
        request: Request,
        id: int,
        formData: dict,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
):
    # email, password, role = formData.get('email'), formData.get('password'), int(formData.get('role'))
    name, database_name, access_token, user_id, host_id = formData.get('name'), formData.get('databaseName'),\
                                                          formData.get('accessToken'), formData.get('userID'), formData.get('hostID'),

    config = (await session.execute(select(Config).where(Config.id == id))).scalars().first()

    if name:
        config.name = name
    if database_name:
        config.database_name = database_name
    if access_token:
        config.access_token = access_token
    if user_id:
        config.user_id = user_id
    if host_id:
        config.host_id = host_id

    print(config.name)

    await session.commit()

    return {
        "status": 200,
        "message": f"Updated config with id: {id}",
    }


@router.delete("/config/{config_id}")
async def delete_config(
        request: Request,
        config_id: int,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
):
    stmt = select(Config).where(Config.id==config_id)
    config_obj = (await session.execute(stmt)).scalar()

    if not config_obj:
        raise HTTPException(status_code=404, detail="Config not found")

    await session.delete(config_obj)
    await session.commit()

    return {
        "status": 200,
        "message": f"delete config ID: {config_id}"
    }








    




