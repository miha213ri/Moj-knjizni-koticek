from datetime import date, datetime
from sqlalchemy import (
    String, Integer, Text, Date, DateTime, Boolean, ForeignKey,
    UniqueConstraint, LargeBinary
)
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

BLOB_TYPE = LargeBinary().with_variant(MEDIUMBLOB(), "mysql")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(250), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    books: Mapped[list["Book"]] = relationship(back_populates="location")
    rooms: Mapped[list["Room"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="USER", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    locations: Mapped[list["UserLocation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    family_member: Mapped["FamilyMember | None"] = relationship(back_populates="user", uselist=False)


class UserLocation(Base):
    __tablename__ = "user_locations"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)
    user: Mapped["User"] = relationship(back_populates="locations")
    location: Mapped["Location"] = relationship()


class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    location: Mapped["Location"] = relationship(back_populates="rooms")
    cabinets: Mapped[list["Cabinet"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("location_id", "name"),)


class Cabinet(Base):
    __tablename__ = "cabinets"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    room: Mapped["Room"] = relationship(back_populates="cabinets")
    shelves: Mapped[list["Shelf"]] = relationship(back_populates="cabinet", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("room_id", "name"),)


class Shelf(Base):
    __tablename__ = "shelves"
    id: Mapped[int] = mapped_column(primary_key=True)
    cabinet_id: Mapped[int] = mapped_column(ForeignKey("cabinets.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    cabinet: Mapped["Cabinet"] = relationship(back_populates="shelves")
    __table_args__ = (UniqueConstraint("cabinet_id", "name"),)


class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, index=True)


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    inventory_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    subtitle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    publication_place: Mapped[str | None] = mapped_column(String(150), nullable=True)
    language: Mapped[str | None] = mapped_column(String(80), nullable=True)
    genre_id: Mapped[int | None] = mapped_column(ForeignKey("genres.id"), nullable=True)
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id"), nullable=True)
    special_edition: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[str | None] = mapped_column(String(30), nullable=True)
    acquisition_source: Mapped[str | None] = mapped_column(String(150), nullable=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    cabinet_id: Mapped[int | None] = mapped_column(ForeignKey("cabinets.id"), nullable=True)
    shelf_id: Mapped[int | None] = mapped_column(ForeignKey("shelves.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    location: Mapped["Location"] = relationship(back_populates="books")
    genre: Mapped["Genre | None"] = relationship()
    collection: Mapped["Collection | None"] = relationship()
    room: Mapped["Room | None"] = relationship()
    cabinet: Mapped["Cabinet | None"] = relationship()
    shelf: Mapped["Shelf | None"] = relationship()
    authors: Mapped[list["BookAuthor"]] = relationship(back_populates="book", cascade="all, delete-orphan")
    isbns: Mapped[list["BookISBN"]] = relationship(back_populates="book", cascade="all, delete-orphan")
    loans: Mapped[list["Loan"]] = relationship(back_populates="book", cascade="all, delete-orphan")
    readings: Mapped[list["ReadingRecord"]] = relationship(back_populates="book", cascade="all, delete-orphan")
    cover_image: Mapped["CoverImage | None"] = relationship(back_populates="book", uselist=False, cascade="all, delete-orphan")


class CoverImage(Base):
    __tablename__ = "cover_images"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    image_data: Mapped[bytes] = mapped_column(BLOB_TYPE)
    mime_type: Mapped[str] = mapped_column(String(50), default="image/webp")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    book: Mapped["Book"] = relationship(back_populates="cover_image")


class BookAuthor(Base):
    __tablename__ = "book_authors"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    book: Mapped["Book"] = relationship(back_populates="authors")
    author: Mapped["Author"] = relationship()


class BookISBN(Base):
    __tablename__ = "book_isbns"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    isbn: Mapped[str] = mapped_column(String(20), index=True)
    book: Mapped["Book"] = relationship(back_populates="isbns")


class Borrower(Base):
    __tablename__ = "borrowers"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(250), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(250), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    loans: Mapped[list["Loan"]] = relationship(back_populates="borrower")


class Loan(Base):
    __tablename__ = "loans"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    borrower_id: Mapped[int] = mapped_column(ForeignKey("borrowers.id"), index=True)
    loan_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    returned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    book: Mapped["Book"] = relationship(back_populates="loans")
    borrower: Mapped["Borrower"] = relationship(back_populates="loans")


class FamilyMember(Base):
    __tablename__ = "family_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    readings: Mapped[list["ReadingRecord"]] = relationship(back_populates="member")
    wishes: Mapped[list["Wishlist"]] = relationship(back_populates="member")
    user: Mapped["User | None"] = relationship(back_populates="family_member")


class ReadingRecord(Base):
    __tablename__ = "reading_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True)
    external_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("family_members.id"), index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    finish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=True)
    book: Mapped["Book | None"] = relationship(back_populates="readings")
    member: Mapped["FamilyMember"] = relationship(back_populates="readings")


class Wishlist(Base):
    __tablename__ = "wishlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("family_members.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    author: Mapped[str | None] = mapped_column(String(250), nullable=True)
    isbn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    genre_id: Mapped[int | None] = mapped_column(ForeignKey("genres.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="Srednja")
    status: Mapped[str] = mapped_column(String(30), default="Želja")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    member: Mapped["FamilyMember"] = relationship(back_populates="wishes")
    genre: Mapped["Genre | None"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
