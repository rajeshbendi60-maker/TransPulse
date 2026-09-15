class FavoriteMapper:
    @staticmethod
    def to_response(favorite):
        return {
            "id": favorite.id,
            "type": favorite.type,
            "category": favorite.category,
            "title": favorite.title,
            "subtitle": favorite.subtitle,
            "routeId": favorite.route_id,
            "stopId": favorite.stop_id,
            "latitude": favorite.latitude,
            "longitude": favorite.longitude,
            "icon": favorite.icon,
            "color": favorite.color,
            "sortOrder": favorite.sort_order,
            "status": favorite.status,
            "lastUsed": favorite.last_used.isoformat() if favorite.last_used else None,
            "usageCount": favorite.usage_count,
            "collectionId": favorite.collection_id,
            "deviceId": favorite.device_id,
            "createdAt": favorite.created_at.isoformat() if favorite.created_at else None,
            "updatedAt": favorite.updated_at.isoformat() if favorite.updated_at else None
        }

    @staticmethod
    def from_request(data, favorite=None):
        # Maps incoming JSON to SQLAlchemy fields
        if not favorite:
            from models import Favorite
            favorite = Favorite()
            
        if "id" in data:
            favorite.id = data["id"]
        if "type" in data:
            favorite.type = data["type"]
        if "category" in data:
            favorite.category = data["category"]
        if "title" in data:
            favorite.title = data["title"]
        if "subtitle" in data:
            favorite.subtitle = data["subtitle"]
        if "routeId" in data:
            favorite.route_id = data["routeId"]
        if "stopId" in data:
            favorite.stop_id = data["stopId"]
        if "latitude" in data:
            favorite.latitude = data["latitude"]
        if "longitude" in data:
            favorite.longitude = data["longitude"]
        if "icon" in data:
            favorite.icon = data["icon"]
        if "color" in data:
            favorite.color = data["color"]
        if "sortOrder" in data:
            favorite.sort_order = data["sortOrder"]
        if "status" in data:
            favorite.status = data["status"]
        if "usageCount" in data:
            favorite.usage_count = data["usageCount"]
        if "collectionId" in data:
            favorite.collection_id = data["collectionId"]
        if "deviceId" in data:
            favorite.device_id = data["deviceId"]
            
        # We don't map lastUsed, createdAt, updatedAt from request usually, except for sync conflicts.
        # But since Android is offline-first, the Android timestamp IS the source of truth if it's newer.
        from datetime import datetime
        if "updatedAt" in data and data["updatedAt"]:
            try:
                # Handle isoformat
                favorite.updated_at = datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00"))
            except Exception:
                pass
        if "lastUsed" in data and data["lastUsed"]:
            try:
                favorite.last_used = datetime.fromisoformat(data["lastUsed"].replace("Z", "+00:00"))
            except Exception:
                pass
                
        return favorite
# TP-v2.0-Release
