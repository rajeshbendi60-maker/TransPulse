from models import Favorite, db
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

class FavoriteService:
    @staticmethod
    def get_favorites(user_id):
        return Favorite.query.filter_by(user_id=user_id, status="ACTIVE").order_by(Favorite.sort_order).all()

    @staticmethod
    def get_favorite_by_id(favorite_id, user_id):
        return Favorite.query.filter_by(id=favorite_id, user_id=user_id).first()

    @staticmethod
    def create_or_update_favorite(user_id, favorite_data, mapper):
        favorite_id = favorite_data.get("id")
        existing = Favorite.query.filter_by(id=favorite_id, user_id=user_id).first() if favorite_id else None
        
        # Conflict resolution if existing exists
        if existing:
            # Check updatedAt
            client_updated_at = favorite_data.get("updatedAt")
            if client_updated_at:
                from datetime import datetime
                try:
                    client_dt = datetime.fromisoformat(client_updated_at.replace("Z", "+00:00"))
                    if existing.updated_at and client_dt < existing.updated_at:
                        # Server is newer, ignore client update
                        return existing, False
                    if existing.updated_at and client_dt == existing.updated_at:
                        # Tie break by deviceId
                        client_device = favorite_data.get("deviceId", "")
                        server_device = existing.device_id or ""
                        if server_device and client_device and client_device < server_device:
                            return existing, False
                except ValueError:
                    pass
            
            # Map new data
            favorite = mapper.from_request(favorite_data, existing)
            is_new = False
        else:
            favorite = mapper.from_request(favorite_data)
            favorite.user_id = user_id
            is_new = True

        try:
            if is_new:
                db.session.add(favorite)
            db.session.commit()
            return favorite, True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error saving favorite: {str(e)}")
            raise e

    @staticmethod
    def delete_favorite(favorite_id, user_id):
        favorite = Favorite.query.filter_by(id=favorite_id, user_id=user_id).first()
        if favorite:
            favorite.status = "DELETED"
            try:
                db.session.commit()
                return True
            except SQLAlchemyError:
                db.session.rollback()
        return False

    @staticmethod
    def reorder_favorites(user_id, reorder_data):
        # reorder_data is list of {"id": "...", "sortOrder": 1}
        try:
            for item in reorder_data:
                fav = Favorite.query.filter_by(id=item.get("id"), user_id=user_id).first()
                if fav:
                    fav.sort_order = item.get("sortOrder", fav.sort_order)
            db.session.commit()
            return True
        except SQLAlchemyError:
            db.session.rollback()
            return False
# TP-v2.0-Release
