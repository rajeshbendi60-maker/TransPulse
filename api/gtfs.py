from flask import Blueprint, jsonify
from services.gtfs_service import GTFSRouteService, GTFSStopService
from mappers.gtfs_mapper import GTFSMapper

gtfs_bp = Blueprint("gtfs_bp", __name__, url_prefix="/api/v1/gtfs")

def success_response(data):
    return jsonify({
        "success": True,
        "message": "Success",
        "data": data
    })

def error_response(msg, status_code=404):
    return jsonify({
        "success": False,
        "message": msg,
        "data": None
    }), status_code

@gtfs_bp.route("/routes", methods=["GET"])
def get_routes():
    routes = GTFSRouteService.get_routes()
    response_data = [GTFSMapper.to_route_response(r) for r in routes]
    return success_response(response_data)

@gtfs_bp.route("/routes/<route_id>", methods=["GET"])
def get_route(route_id):
    route = GTFSRouteService.get_route_by_id(route_id)
    if not route:
        return error_response("Route not found")
    return success_response(GTFSMapper.to_route_response(route))

@gtfs_bp.route("/routes/<route_id>/stops", methods=["GET"])
def get_route_stops(route_id):
    stops = GTFSRouteService.get_stops(route_id)
    response_data = [GTFSMapper.to_stop_response(s) for s in stops]
    return success_response(response_data)

@gtfs_bp.route("/routes/<route_id>/shape", methods=["GET"])
def get_route_shape(route_id):
    shapes = GTFSRouteService.get_shape(route_id)
    response_data = [GTFSMapper.to_shape_response(s) for s in shapes]
    return success_response(response_data)

@gtfs_bp.route("/routes/<route_id>/trips", methods=["GET"])
def get_route_trips(route_id):
    trips = GTFSRouteService.get_trips(route_id)
    response_data = [GTFSMapper.to_trip_response(t) for t in trips]
    return success_response(response_data)

@gtfs_bp.route("/routes/<route_id>/overview", methods=["GET"])
def get_route_overview(route_id):
    route, stops, shapes, trips, stats = GTFSRouteService.get_overview(route_id)
    if not route:
        return error_response("Route not found")
    
    response_data = GTFSMapper.to_overview_response(route, stops, shapes, trips, stats)
    return success_response(response_data)

@gtfs_bp.route("/stops", methods=["GET"])
def get_stops():
    # Helper to get all stops (optional, but matching Android api /api/v1/gtfs/stops)
    # the user hasn't explicitly listed this in the phase, but Android calls this to sync stops.
    from models import Stop
    stops = Stop.query.limit(200).all() # Limit to prevent crash
    response_data = [GTFSMapper.to_stop_response(s) for s in stops]
    return success_response(response_data)

@gtfs_bp.route("/stops/<stop_id>", methods=["GET"])
def get_stop(stop_id):
    stop = GTFSStopService.get_stop_by_id(stop_id)
    if not stop:
        return error_response("Stop not found")
    return success_response(GTFSMapper.to_stop_response(stop))

@gtfs_bp.route("/stops/<stop_id>/routes", methods=["GET"])
def get_stop_routes(stop_id):
    routes = GTFSStopService.get_routes_for_stop(stop_id)
    response_data = [GTFSMapper.to_route_response(r) for r in routes]
    return success_response(response_data)

@gtfs_bp.route("/stops/nearby", methods=["GET"])
def get_nearby_stops():
    from flask import request
    from models import Stop
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    limit = request.args.get("limit", default=20, type=int)
    stops = Stop.query.limit(limit).all()
    response_data = [GTFSMapper.to_stop_response(s) for s in stops]
    return success_response({"stops": response_data})
