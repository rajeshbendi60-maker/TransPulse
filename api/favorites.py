from flask import Blueprint, request, jsonify
from flask_login import current_user
from services.favorite_service import FavoriteService
from mappers.favorite_mapper import FavoriteMapper
from flask_login import current_user, login_required
import logging

logger = logging.getLogger(__name__)

favorites_bp = Blueprint("favorites", __name__, url_prefix="/api/v1/favorites")

@favorites_bp.route("", methods=["GET"])
@login_required
def get_favorites():
    try:
        favorites = FavoriteService.get_favorites(current_user.id)
        return jsonify({
            "success": True,
            "data": [FavoriteMapper.to_response(f) for f in favorites]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching favorites: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@favorites_bp.route("", methods=["POST"])
@login_required
def create_favorite():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid payload"}), 400
            
        favorite, _ = FavoriteService.create_or_update_favorite(current_user.id, data, FavoriteMapper)
        
        return jsonify({
            "success": True,
            "data": FavoriteMapper.to_response(favorite)
        }), 201
    except Exception as e:
        logger.error(f"Error creating favorite: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@favorites_bp.route("/<favorite_id>", methods=["GET"])
@login_required
def get_favorite(favorite_id):
    try:
        favorite = FavoriteService.get_favorite_by_id(favorite_id, current_user.id)
        if not favorite:
            return jsonify({"success": False, "error": "Favorite not found"}), 404
            
        return jsonify({
            "success": True,
            "data": FavoriteMapper.to_response(favorite)
        }), 200
    except Exception as e:
        logger.error(f"Error fetching favorite: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@favorites_bp.route("/<favorite_id>", methods=["PATCH"])
@login_required
def update_favorite(favorite_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid payload"}), 400
            
        data["id"] = favorite_id
        favorite, updated = FavoriteService.create_or_update_favorite(current_user.id, data, FavoriteMapper)
        
        return jsonify({
            "success": True,
            "data": FavoriteMapper.to_response(favorite)
        }), 200
    except Exception as e:
        logger.error(f"Error updating favorite: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@favorites_bp.route("/<favorite_id>", methods=["DELETE"])
@login_required
def delete_favorite(favorite_id):
    try:
        success = FavoriteService.delete_favorite(favorite_id, current_user.id)
        if not success:
            return jsonify({"success": False, "error": "Favorite not found or could not be deleted"}), 404
            
        return jsonify({"success": True, "message": "Favorite deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error deleting favorite: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@favorites_bp.route("/reorder", methods=["POST"])
@login_required
def reorder_favorites():
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"success": False, "error": "Invalid payload, expected array"}), 400
            
        success = FavoriteService.reorder_favorites(current_user.id, data)
        if success:
            return jsonify({"success": True, "message": "Favorites reordered successfully"}), 200
        else:
            return jsonify({"success": False, "error": "Failed to reorder favorites"}), 500
    except Exception as e:
        logger.error(f"Error reordering favorites: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500
# TP-v2.0-Release
