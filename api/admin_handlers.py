from io import BytesIO
from typing import Optional

from apscheduler.triggers.cron import CronTrigger
from fastapi import UploadFile, Request
from fastapi import status
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Request
from sqlalchemy import and_, delete, select, or_, update, insert
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.auth_config import current_user, RoleChecker, PermissionRoleChecker
from api.auth.exceptions import InvalidEmail
from api.auth.manager import get_user_manager, UserManager
from api.auth.models import User
from api.auth.schemas import UserCreate
from api.config.models import Config, Group, List, ListLrSearchSystem, ListURI, LiveSearchList, LiveSearchListQuery \
    , UserQueryCount, YandexLr, Role, AutoUpdatesMode
from api.config.utils import get_all_configs, get_all_groups, get_all_groups_for_user, get_all_roles, get_all_user, \
    get_config_names, get_group_names, get_groups_names_dict, get_lists_names, get_live_search_lists_names, update_list
from api.schemas import AutoUpdatesScheduleRead, AutoUpdatesScheduleCreate
from api.config.models import LiveSearchAutoUpdateSchedule
from api.query_api.router import router as query_router
from api.url_api.router import router as url_router
from api.history_api.router import router as history_router
from api.merge_api.router import router as merge_router
from api.live_search_api.router import router as live_search_router
from db.session import get_db_general
from utils import CommaNewLineSeparatedValues, import_users_from_excel
import config
from config import MONTHLY_REQUEST_LIMIT
import const
from scheduler import scheduler

admin_router = APIRouter()

admin_router.include_router(query_router, prefix="/query")
admin_router.include_router(url_router, prefix="/url")
admin_router.include_router(history_router, prefix="/history")
admin_router.include_router(merge_router, prefix="/merge")
admin_router.include_router(live_search_router, prefix="/live_search_list")

templates = Jinja2Templates(directory="static")


def pad_list_with_zeros_excel(lst, amount):
    if len(lst) < amount:
        padding = [0] * (amount - len(lst))
        lst.extend(padding)
    return lst


def pad_list_with_zeros(lst, amount):
    if len(lst) < amount:
        padding = [f"""<div style='height: 55px; width: 100px; margin: 0px; padding: 0px; background-color: #B9BDBC'>
            <span style='font-size: 18px'><span style='color:red'>NAN</span></span><br>
            <span style='font-size: 10px'>Клики</span><span style='font-size: 10px; margin-left: 20px'>CTR <span style='color:red'>NAN%</span></span><br>
            <span style='font-size: 10px'><span style='color:red'>NAN</span></span> <span style='font-size: 10px; margin-left: 30px'>R <span style='color:red'>NAN%</span></span>
            </div>"""] * (amount - len(lst))
        lst.extend(padding)
    return lst


@admin_router.get("/")
async def login_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("login.html", {"request": request, "user": user})


@admin_router.get("/register")
async def register(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("register.html", {"request": request, "user": user})


@admin_router.get("/profile/{username}")
async def show_profile(request: Request,
                       username: str,
                       user=Depends(current_user),
                       session: AsyncSession = Depends(get_db_general),
                       #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser"}))
                       ):
    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]

    group_names = await get_group_names(session, user)

    return templates.TemplateResponse("profile.html",
                                      {"request": request,
                                       "user": user,
                                       "config_names": config_names,
                                       "group_names": group_names})


@admin_router.get("/superuser/{username}")
async def show_superuser(
        request: Request,
        user=Depends(current_user),
        session: AsyncSession = Depends(get_db_general),
        #required: bool = Depends(RoleChecker(required_permissions={"Superuser"}))
):
    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]

    all_configs = [elem for elem in (await get_all_configs(session))]

    group_names = await get_group_names(session, user)

    return templates.TemplateResponse("superuser.html",
                                      {"request": request,
                                       "user": user,
                                       "config_names": config_names,
                                       "group_names": group_names,
                                       "all_configs": all_configs,})


@admin_router.get("/list/{username}")
async def show_list(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser"}))
):
    config_id = request.session["config"]["config_id"]
    group_id = request.session["group"]["group_id"]

    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)
    list_names = await get_lists_names(session, user, request.session["group"].get("name", ""), config_id, group_id)

    groups = (await session.execute(select(Group.id, Group.name))).all()
    group_dict = {group.id: group.name for group in groups}
    configs = (await session.execute(select(Config.id, Config.name))).all()
    config_dict = {config.id: config.name for config in configs}
    users = (await session.execute(select(User.id, User.username))).all()
    user_dict = {user.id: user.username for user in users}

    return templates.TemplateResponse("lists.html",
                                      {"request": request,
                                       "user": user,
                                       "config_names": config_names,
                                       "group_names": group_names,
                                       "list_names": list_names,
                                       "group_dict": group_dict,
                                       "config_dict": config_dict,
                                       "name_dict": user_dict,
                                       })


@admin_router.post("/list")
async def add_list(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Administrator", "Superuser"}))
):

    group_name, config_name, list_name, uri_list, is_public = data.values()

    group_id = (await session.execute(select(Group.id).where(Group.name == group_name))).scalars().first()
    config_id = (await session.execute(select(Config.id).where(Config.name == config_name))).scalars().first()

    new_list = List(
        name=list_name,
        author=user.id,
        is_public=is_public,
        group=group_id,
        config=config_id,
    )

    new_uris = [ListURI(uri=uri.strip(), list=new_list) for uri in uri_list]

    try:
        session.add(new_list)
        session.add_all(new_uris)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return JSONResponse(
            status_code=400,
            content={"error": "An error occurred while adding the list. Possibly due to database constraints."}
        )
    except Exception as e:
        await session.rollback()
        return JSONResponse(
            status_code=500,
            content={"error": f"An unexpected error occurred: {str(e)}"}
        )

    return {
        "status": "success",
        "message": f"List '{list_name}' created successfully",
        "list_id": new_list.id
    }


@admin_router.put("/list")
async def change_list_visibility(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Administrator", "Superuser"}))
):
    
    is_public = data["is_public"]
    list_name = data["name"]

    if is_public is None or list_name is None:
        raise HTTPException(status_code=400, detail="Both 'is_public' and 'name' must be provided")

    # Выполнение запроса для получения списка с указанным именем
    result = await session.execute(select(List).where(List.name == list_name))
    list_item = result.scalars().first()

    # Проверяем, существует ли список
    if not list_item:
        raise HTTPException(status_code=404, detail="List not found")

    # Обновление is_public в зависимости от входных данных
    list_item.is_public = is_public
    await session.commit()

    return {
        "status": 200,
        "message": f"Changed 'is_public' for {list_item.name} to {is_public}"
    }


@admin_router.delete("/list")
async def delete_list(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Administrator", "Superuser"}))
):
    list_name = data["name"]

    # Получаем объект списка
    result = await session.execute(select(List).where(List.name == list_name))
    list_to_delete = result.scalars().first()

    if list_to_delete:
        # Удаляем все связанные записи в list_uri
        await session.execute(delete(ListURI).where(ListURI.list_id == list_to_delete.id))

        # Удаляем объект списка
        await session.delete(list_to_delete)
        await session.commit()  # Сохраняем изменения

        return {
            "status": 200,
            "message": f"Successfully deleted list '{list_name}'"
        }
    else:
        return {
            "status": 404,
            "message": f"List '{list_name}' not found"
        }


@admin_router.get("/list/{list_id}/edit")
async def show_edit_list(
    request: Request,
    list_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser"}))
):

    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)

    groups = (await session.execute(select(Group.id, Group.name))).all()
    group_dict = {group.id: group.name for group in groups}
    configs = (await session.execute(select(Config.id, Config.name))).all()
    config_dict = {config.id: config.name for config in configs}

    uri_list = (await session.execute(select(ListURI.uri).where(ListURI.list_id == list_id))).scalars().all()

    return templates.TemplateResponse("edit_list.html",
                                      {"request": request,
                                       "user": user,
                                       "config_names": config_names,
                                       "group_names": group_names,
                                       "group_dict": group_dict,
                                       "config_dict": config_dict,
                                       "uri_list":uri_list,
                                       "list_id": list_id,
                                       })


@admin_router.delete("/list/{list_id}/edit")
async def delete_list_record(
    request: Request,
    list_id: int,
    uri: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser"}))
):
    uri_model = (await session.execute(select(ListURI).where(and_(ListURI.uri == uri["uri"], ListURI.list_id == list_id)))).scalars().first()

    await session.delete(uri_model)

    await session.commit()

    return {
        "status": 200,
        "message": f"delete {uri} record from {list_id} list"
    }


@admin_router.put("/list/{list_id}/edit")
async def change_list_record(
    request: Request,
    list_id: int,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser"}))
):
    print(data)

    old_uri, new_uri = data.values()

    uri_model = (await session.execute(select(ListURI).where(and_(ListURI.uri == old_uri, ListURI.list_id == list_id)))).scalars().first()

    uri_model.uri = new_uri

    await session.commit()
    
    return {
        "status": 200,
        "message": f"change uri from {old_uri} to {new_uri}"
    }


@admin_router.post("/list/{list_id}/edit")
async def add_uri(
    request: Request,
    list_id: int,   
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser"}))
):
    record = ListURI(
        uri=data["uri"].strip(),
        list_id=list_id
    )

    session.add(record)

    await session.commit()

    return {
        "status": 200,
        "message": f"add {data['uri']} record to {list_id} list"
    }


@admin_router.get("/live_search/{username}")
async def show_live_search(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    config_id = request.session["config"]["config_id"]
    group_id = request.session["group"]["group_id"]

    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)
    list_names = await get_live_search_lists_names(session, user)

    return templates.TemplateResponse("live_search.html",
                                      {"request": request,
                                       "user": user,
                                       "config_names": config_names,
                                       "group_names": group_names,  
                                       "list_names": list_names,
                                       })


@admin_router.post("/live_search")
async def add_live_search_list(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Administrator", "Superuser", "Search", "User"})),
    required: bool = Depends(PermissionRoleChecker({"access_list_panel_create"})),
):

    main_domain, list_name, query_list = data.values()

    new_list = LiveSearchList(
        name=list_name,
        author=user.id,
        main_domain=main_domain,
    )

    try:
        session.add(new_list)
        await session.flush()

        new_queries = [
            LiveSearchListQuery(query=query.strip(), list_id=new_list.id)
            for query in query_list
        ]

        session.add_all(new_queries)
        await session.commit()
        
    except IntegrityError:
        await session.rollback()
        return JSONResponse(
            status_code=400,
            content={"error": "An error occurred while adding the list. Possibly due to database constraints."}
        )
    except Exception as e:
        await session.rollback()
        return JSONResponse(
            status_code=500,
            content={"error": f"An unexpected error occurred: {str(e)}"}
        )

    return {
        "status": "success",
        "message": f"List '{list_name}' created successfully",
        "list_id": new_list.id
    }


@admin_router.delete("/live_search")
async def delete_live_search_list(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Administrator", "Superuser", "Search"}))
):
    list_name = data["name"]

    # Получаем объект списка
    result = await session.execute(select(LiveSearchList).where(LiveSearchList.name == list_name))
    list_to_delete = result.scalars().first()

    if list_to_delete:
        # Удаляем объект списка
        await session.delete(list_to_delete)
        await session.commit()  # Сохраняем изменения

        return {
            "status": 200,
            "message": f"Successfully deleted list '{list_name}'"
        }
    else:
        return {
            "status": 404,
            "message": f"List '{list_name}' not found"
        }


@admin_router.get("/live_search/{list_id}/edit")
async def show_edit_live_search(
    request: Request,
    list_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):

    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)

    query_list = (await session.execute(select(LiveSearchListQuery.query).where(LiveSearchListQuery.list_id == list_id))).scalars().all()

    print(query_list)

    return templates.TemplateResponse("live_search_edit.html",
                                      {"request": request,
                                       "user": user,
                                       "config_names": config_names,
                                       "group_names": group_names,
                                       "query_list":query_list,
                                       "list_id": list_id,
                                       })



@admin_router.delete("/live_search/{list_id}/edit")
async def delete_live_search_record(
    request: Request,
    list_id: int,
    query: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    query_model = (await session.execute(select(LiveSearchListQuery).where(and_(LiveSearchListQuery.query == query["query"], LiveSearchListQuery.list_id == list_id)))).scalars().first()

    await session.delete(query_model)

    await session.commit()

    return {
        "status": 200,
        "message": f"delete {query} record from {list_id} list"
    }


@admin_router.put("/live_search/{list_id}/edit")
async def change_live_search_record(
    request: Request,
    list_id: int,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    print(data)

    old_uri, new_uri = data.values()

    query_model = (await session.execute(select(LiveSearchListQuery).where(and_(LiveSearchListQuery.query == old_uri, LiveSearchListQuery.list_id == list_id)))).scalars().first()

    query_model.query = new_uri

    await session.commit()
    
    return {
        "status": 200,
        "message": f"change query from {old_uri} to {new_uri}"
    }


@admin_router.post("/live_search/{list_id}/edit")
async def add_live_search_record(
    request: Request,
    list_id: int,   
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    record = LiveSearchListQuery(
        query=data["uri"].strip(),
        list_id=list_id
    )

    session.add(record)

    await session.commit()

    return {
        "status": 200,
        "message": f"add {data['uri']} record to {list_id} list"
    }


@admin_router.get("/list_menu")
async def show_list_menu(
    request: Request,
    list_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)

    list_name = (await session.execute(select(LiveSearchList.name).where(LiveSearchList.id == list_id))).scalars().first()

    yandex_list = (await session.execute(select(ListLrSearchSystem).where(and_(ListLrSearchSystem.list_id == list_id, ListLrSearchSystem.search_system == "Yandex")))).scalars().all()
    google_list = (await session.execute(select(ListLrSearchSystem).where(and_(ListLrSearchSystem.list_id == list_id, ListLrSearchSystem.search_system == "Google")))).scalars().all()

    regions = (await session.execute(select(YandexLr))).scalars().all()
    region_dict = {region.Geoid: region.Geo for region in regions}

    return templates.TemplateResponse("live_search_list.html",
                                    {"request": request,
                                    "user": user,
                                    "config_names": config_names,
                                    "group_names": group_names,
                                    "list_id": list_id,
                                    "list_name": list_name,
                                    "yandex_list": yandex_list,
                                    "google_list": google_list,
                                    "region_dict": region_dict,
                                    })


@admin_router.post("/list_menu")
async def add_lr_list(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    list_id, region_code, search_system = data.values()
    list_id, region_code = int(list_id), int(region_code)

    session.add(ListLrSearchSystem(
        list_id=list_id,
        lr=region_code,
        search_system=search_system,
    ))

    await session.commit()

    return {
        "status": 200,
        "message": f"Add association for {list_id}:\nlr={region_code}\nsearch_system={search_system}"
    }


@admin_router.delete("/list_menu")
async def delete_lr_list(
    request: Request,
    data: dict,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    print(data)
    list_id, region_code, search_system = data.values()
    list_id, region_code = int(list_id), int(region_code)

    res = (await session.execute(select(ListLrSearchSystem).where(
        and_(
            ListLrSearchSystem.list_id == list_id, 
            ListLrSearchSystem.lr == region_code, 
            ListLrSearchSystem.search_system == search_system)))).scalars().first()
    
    await session.delete(res)

    await session.commit()

    return {
        "status": 200,
        "message": f"Delete association for {list_id}:\nlr={region_code}\nsearch_system={search_system}"
    }
@admin_router.put("/reset_query_limits/")
async def reset_query_limits(
    #request: Request,
    session: AsyncSession = Depends(get_db_general),
    #user=Depends(current_user),
    #required: bool = Depends(RoleChecker(required_permissions={"Superuser"}))                      
):

    query_limit = const.query_value
    active_users = await session.execute(
        select(User).join(Role).where(
            User.is_active == True,
            or_(Role.name == 'Search', Role.name == 'Superuser')
        )
    )
    active_users_list = active_users.scalars().all()

    for user in active_users_list:
        user_query_count = await session.execute(
            select(UserQueryCount).where(UserQueryCount.user_id == user.id)
        )
        user_query_count_record = user_query_count.scalars().first()
        user_query_count_record.query_count = query_limit

    await session.commit()
    return {
        "status": 200,
        "message": f"Reset query limits successfully"
    }

@admin_router.get("/list_menu/regions")
async def get_regions(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"User", "Administrator", "Superuser", "Search"}))
):
    regions = (await session.execute(select(YandexLr))).scalars().all()
    region_dict = {region.Geo: region.Geoid for region in regions}
    return region_dict


@admin_router.get("/user_menu")
async def show_user_menu(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Superuser"}))
):    
    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)

    all_users = await get_all_user(session)   


    all_roles_dict = await get_all_roles(session)

    all_roles_dict_reverse = {value: key for key, value in all_roles_dict.items()}

    all_roles_names = all_roles_dict.values()

    groups_dict = await get_groups_names_dict(session)

    groups_dict_reverse = {value: key for key, value in groups_dict.items()}

    groups_dict_names = groups_dict.values()

    return templates.TemplateResponse("user_menu.html",
                                    {"request": request,
                                    "user": user,
                                    "config_names": config_names,
                                    "group_names": group_names,
                                    "all_users": all_users,
                                    "all_roles_dict": all_roles_dict,
                                    "all_roles_names": all_roles_names,
                                    "all_roles_dict_reverse": all_roles_dict_reverse,
                                    "groups_dict_names": groups_dict_names,
                                    "groups_dict": groups_dict,
                                    "groups_dict_reverse": groups_dict_reverse, 
                                    })



@admin_router.get("/group_menu")
async def show_group_menu(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_db_general),
    #required: bool = Depends(RoleChecker(required_permissions={"Superuser"}))
):
    group_name = request.session["group"].get("name", "")
    config_names = [elem[0] for elem in (await get_config_names(session, user, group_name))]
    group_names = await get_group_names(session, user)

    all_users = await get_all_user(session)

    all_roles_dict = await get_all_roles(session)

    all_roles_dict_reverse = {value: key for key, value in all_roles_dict.items()}

    all_roles_names = all_roles_dict.values()

    groups_dict = await get_groups_names_dict(session)

    groups_dict_reverse = {value: key for key, value in groups_dict.items()}

    groups_dict_names = groups_dict.values()

    all_groups = await get_all_groups(session)

    all_configs = await get_all_configs(session)

    return templates.TemplateResponse("group_menu.html",
                                    {"request": request,
                                    "user": user,
                                    "config_names": config_names,
                                    "group_names": group_names,
                                    "all_users": all_users,
                                    "all_roles_dict": all_roles_dict,
                                    "all_roles_names": all_roles_names,
                                    "all_roles_dict_reverse": all_roles_dict_reverse,
                                    "groups_dict_names": groups_dict_names,
                                    "groups_dict": groups_dict,
                                    "groups_dict_reverse": groups_dict_reverse, 
                                    "all_groups": all_groups,
                                    "all_configs": all_configs,
                                    })


@admin_router.post("/batch_register_excel")
async def batch_register_excel(
        request: Request,
        file: UploadFile,
        user_manager: AsyncSession = Depends(get_user_manager),
        #required: bool = Depends(RoleChecker({"Superuser"})),
        status_code=status.HTTP_201_CREATED):
    try:
        file = await file.read()
        await user_manager.batch_create(import_users_from_excel(BytesIO(file)))
    except InvalidEmail as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail) 
    except IntegrityError as e:
        info = e.orig.args[0]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=info[info.rfind("DETAIL"):]) 

    return JSONResponse({
        "status": "success",
        "detail": "Users created successfully",
    }, status_code)


@admin_router.post("/batch_register")
async def batch_register(
        request: Request,
        user: User = Depends(current_user),
        user_manager: UserManager = Depends(get_user_manager),
        #required: bool = Depends(RoleChecker(required_permissions={"Superuser"})),
        status_code=status.HTTP_201_CREATED):
    body_bytes = await request.body()
    raw_users = body_bytes.decode("UTF-8")
    reader = CommaNewLineSeparatedValues().reader(raw_users)
    try:
        await user_manager.batch_create(
            map(lambda user_create: 
                    UserCreate(
                        id=-1, 
                        email=user_create[0],
                        # username is None when it's empty string
                        username=user_create[1] or None,
                        password=user_create[2]),
                    reader)
                )
    except InvalidEmail as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail) 
    except IntegrityError as e:
        info = e.orig.args[0]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=info[info.rfind("DETAIL"):]) 

    return JSONResponse({
        "status": "success",
        "detail": "Users created successfully",
    }, status_code)


@admin_router.post("/list_menu/{list_id}/updates_schedule", status_code=status.HTTP_200_OK)
async def create_or_update_list_updates_schedule(
    request: Request,
    list_id: int,
    auto_update_schedule: AutoUpdatesScheduleCreate,
    session: AsyncSession = Depends(get_db_general),
    user: User = Depends(current_user),):
    schedule = await session.execute(
            select(LiveSearchAutoUpdateSchedule)
            .where(LiveSearchAutoUpdateSchedule.list_id == list_id)
        )
    schedule = schedule.scalars().first()
    values = dict(
            list_id=list_id,
            days=",".join(
                map(
                    lambda day: str(day) if auto_update_schedule.mode == AutoUpdatesMode.MonthDays else str(day-1),
                    auto_update_schedule.days,
                )
            ) if auto_update_schedule.days is not None else None,
            mode=auto_update_schedule.mode,
            hours=auto_update_schedule.hours,
            minutes=auto_update_schedule.minutes,
            user_id=user.id)

    if schedule is not None:
        list_updates_schedule = await session.execute(
            update(LiveSearchAutoUpdateSchedule)
            .where(LiveSearchAutoUpdateSchedule.id == schedule.id)
            .values(**values).returning(
                LiveSearchAutoUpdateSchedule
            )
        )
    else:
        list_updates_schedule = await session.execute(
            insert(LiveSearchAutoUpdateSchedule).values(**values).returning(LiveSearchAutoUpdateSchedule)
        )

    list_updates_schedule: LiveSearchAutoUpdateSchedule = list_updates_schedule.scalars().first()
    schedule_id = str(list_updates_schedule.id)
    if scheduler.get_job(schedule_id) is not None:
        scheduler.remove_job(schedule_id)
    if auto_update_schedule.mode == AutoUpdatesMode.Disabled:
        await session.commit()
        return
    days = list_updates_schedule.days.split(",")
    scheduler.add_job(update_list, id=schedule_id, args=(user, list_id), trigger=CronTrigger(
        hour=list_updates_schedule.hours,
        minute=list_updates_schedule.minutes,
        day_of_week=list_updates_schedule.days if list_updates_schedule.mode == AutoUpdatesMode.WeekDays else None,
        day=list_updates_schedule.days if list_updates_schedule.mode == AutoUpdatesMode.MonthDays else None,
        timezone=scheduler.timezone
    ))
    await session.commit()


@admin_router.get("/list_menu/{list_id}/updates_schedule")
async def get_list_updates_schedule(
    request: Request,
    list_id: int,
    session: AsyncSession = Depends(get_db_general),
    user: User = Depends(current_user)) -> Optional[AutoUpdatesScheduleRead]:
    schedule = await session.execute(
        select(LiveSearchAutoUpdateSchedule).
        where(LiveSearchAutoUpdateSchedule.list_id == list_id)
        )
    schedule = schedule.scalars().first()
    return None if schedule is None else AutoUpdatesScheduleRead(
        id=schedule.id, mode=schedule.mode, days=schedule.days.split(",") if schedule.days else None, hours=schedule.hours, minutes=schedule.minutes
    )

