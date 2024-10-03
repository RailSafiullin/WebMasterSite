import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Integer, ForeignKey, Uuid, Enum
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class GroupConfigAssociation(Base):
    __tablename__ = 'group_config_association'

    group_id = Column(Integer, ForeignKey('group.id'), primary_key=True)
    config_id = Column(Integer, ForeignKey('config.id'), primary_key=True)


class Config(Base):
    __tablename__ = "config"

    id = Column(Integer, autoincrement=True, primary_key=True)
    id_author = Column(Integer, ForeignKey("user.id"), nullable=True)
    name = Column(String, nullable=False)
    database_name = Column(String, nullable=False)
    access_token = Column(String, nullable=False)
    user_id = Column(String, nullable=True)
    host_id = Column(String, nullable=False)

    # Используем строку для связи с Group
    groups = relationship("Group", secondary='group_config_association', back_populates="configs")
    user = relationship("User", primaryjoin="Config.id_author == User.id", lazy="selectin")

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column(String, nullable=False)

    access_queries = Column(Boolean, default=False)
    access_queries_full = Column(Boolean, default=False)
    access_queries_view = Column(Boolean, default=False)
    access_queries_filter = Column(Boolean, default=False)
    access_queries_export = Column(Boolean, default=False)
    access_queries_update = Column(Boolean, default=False)
    access_queries_sum = Column(Boolean, default=False)

    access_url = Column(Boolean, default=False)
    access_url_full = Column(Boolean, default=False)
    access_url_filter = Column(Boolean, default=False)
    access_url_export = Column(Boolean, default=False)
    access_url_update = Column(Boolean, default=False)
    access_url_sum = Column(Boolean, default=False)

    access_history = Column(Boolean, default=False)
    access_history_full = Column(Boolean, default=False)
    access_history_view = Column(Boolean, default=False)
    access_history_export = Column(Boolean, default=False)

    access_url_query_merge = Column(Boolean, default=False)
    access_url_query_merge_full = Column(Boolean, default=False)
    access_url_query_merge_view = Column(Boolean, default=False)
    access_url_query_merge_run = Column(Boolean, default=False)

    access_list_panel = Column(Boolean, default=False)
    access_list_panel_full = Column(Boolean, default=False)
    access_list_panel_create = Column(Boolean, default=False)
    access_list_panel_edit = Column(Boolean, default=False)
    access_list_panel_share = Column(Boolean, default=False)

    access_command_panel = Column(Boolean, default=False)
    access_command_panel_full = Column(Boolean, default=False)
    access_command_panel_own = Column(Boolean, default=False)

    access_live_search = Column(Boolean, default=False)
    access_live_search_full = Column(Boolean, default=False)
    access_live_search_use = Column(Boolean, default=False)

    access_user_menu = Column(Boolean, default=False)
    access_group_menu = Column(Boolean, default=False)


class Group(Base):
    __tablename__ = "group"

    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column(String, nullable=False)
    id_author = Column(Integer, ForeignKey("user.id"), nullable=True)
    # Используем строку для связи с Config и User
    configs = relationship("Config",
                           secondary='group_config_association',
                           back_populates="groups",
                           lazy="selectin"
                           )
    users = relationship("User",
                         secondary='group_user_association', back_populates="groups",
                         lazy="selectin"
                         )
    user = relationship("User", primaryjoin="Group.id_author == User.id", lazy="selectin")

class List(Base):
    __tablename__ = "list"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    author = Column(Integer,ForeignKey("user.id"), nullable=False)
    group = Column(Integer, ForeignKey("group.id"), nullable=False)
    config = Column(Integer, ForeignKey("config.id"), nullable=False)
    is_public = Column(Boolean, nullable=False, default=False)

    uris = relationship("ListURI", back_populates="list")

class ListURI(Base):
    __tablename__ = "list_uri"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uri = Column(String, nullable=False)
    list_id = Column(Integer, ForeignKey("list.id"), nullable=False)

    # Связь с List
    list = relationship("List", back_populates="uris")


class UserQueryCount(Base):
    __tablename__ = "user_query_count"

    user_id = Column(Integer, ForeignKey("user.id", ondelete='CASCADE'), nullable=False, primary_key=True)
    query_count = Column(Integer, nullable=False, default=3000)
    last_update_date = Column(DateTime, nullable=False)
    


class LiveSearchList(Base):
    __tablename__ = "live_search_list"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    author = Column(Integer, ForeignKey("user.id"), nullable=False)
    main_domain = Column(String, nullable=False)

    # Связь с ListLrSearchSystem
    lr_search_systems = relationship("ListLrSearchSystem", back_populates="live_search_list", cascade="all, delete-orphan")

    # Связь с LiveSearchListQuery
    queries = relationship("LiveSearchListQuery", back_populates="live_search_list", cascade="all, delete-orphan")

    auto_updates = relationship("LiveSearchAutoUpdateSchedule", back_populates="live_search_list")

class AutoUpdatesMode(str, enum.Enum):
    Disabled = "Disabled"
    WeekDays = "WeekDays"
    MonthDays = "MonthDays"
    
class LiveSearchAutoUpdateSchedule(Base):
    __tablename__ = "live_search_list_auto_update_schedule"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer,ForeignKey("user.id"), nullable=False)
    list_id = Column(Integer, ForeignKey("live_search_list.id"), nullable=False)
    mode = Column(Enum(AutoUpdatesMode))
    # store days in cron-like format "1,2,3,...,31"
    days = Column(String(100), nullable=True)
    hours = Column(Integer, nullable=True)
    minutes = Column(Integer, nullable=True)

    author = relationship("User", back_populates="lists_auto_updates", cascade="all,delete")
    live_search_list = relationship("LiveSearchList", back_populates="auto_updates", cascade="all,delete")


class ListLrSearchSystem(Base):
    __tablename__ = "list_lr_search_system"

    id = Column(Integer, primary_key=True, autoincrement=True)
    list_id = Column(Integer, ForeignKey("live_search_list.id"), nullable=False)
    lr = Column(Integer, nullable=False)
    search_system = Column(String, nullable=False)

    # Back-reference to LiveSearchList
    live_search_list = relationship("LiveSearchList", back_populates="lr_search_systems")

    # Relationships to QueryLiveSearchYandex and QueryLiveSearchGoogle with cascade delete
    yandex_results = relationship("QueryLiveSearchYandex", back_populates="lr_list", cascade="all, delete-orphan")
    google_results = relationship("QueryLiveSearchGoogle", back_populates="lr_list", cascade="all, delete-orphan")


class LiveSearchListQuery(Base):
    __tablename__ = "live_search_list_query"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String, nullable=False)
    list_id = Column(Integer, ForeignKey("live_search_list.id"), nullable=False)

    # Обратная связь с LiveSearchList
    live_search_list = relationship("LiveSearchList", back_populates="queries")

    # Связи с QueryLiveSearchYandex и QueryLiveSearchGoogle
    yandex_results = relationship("QueryLiveSearchYandex", back_populates="live_search_list_query", cascade="all, delete-orphan")
    google_results = relationship("QueryLiveSearchGoogle", back_populates="live_search_list_query", cascade="all, delete-orphan")


class QueryLiveSearchYandex(Base):
    __tablename__ = "query_live_search_yandex"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("live_search_list_query.id"), nullable=False)
    url = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    date = Column(DateTime, nullable=False)
    lr_list_id = Column(Integer, ForeignKey("list_lr_search_system.id", ondelete="CASCADE"), nullable=False)

    # Back-reference to LiveSearchListQuery
    live_search_list_query = relationship("LiveSearchListQuery", back_populates="yandex_results")

    # Relationship to ListLrSearchSystem with back-population
    lr_list = relationship("ListLrSearchSystem", back_populates="yandex_results")


class QueryLiveSearchGoogle(Base):
    __tablename__ = "query_live_search_google"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("live_search_list_query.id"), nullable=False)
    url = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    date = Column(DateTime, nullable=False)
    lr_list_id = Column(Integer, ForeignKey("list_lr_search_system.id", ondelete="CASCADE"), nullable=False)

    # Back-reference to LiveSearchListQuery
    live_search_list_query = relationship("LiveSearchListQuery", back_populates="google_results")

    # Relationship to ListLrSearchSystem with back-population
    lr_list = relationship("ListLrSearchSystem", back_populates="google_results")



class YandexLr(Base):
    __tablename__ = "yandex_lr"

    id = Column(Integer, primary_key=True, autoincrement=True)
    Geo = Column(String, nullable=False)
    Geoid = Column(Integer, nullable=False)
    
