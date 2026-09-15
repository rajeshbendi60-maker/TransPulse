import random

class PredictionRequest:
    def __init__(self, domain, context):
        self.domain = domain
        self.context = context

class PredictorInterface:
    def predict(self, features):
        pass

class DeterministicPredictor(PredictorInterface):
    def predict(self, features):
        return {"value": "Delay 7 min", "confidence": 94}

class PredictionPipeline:
    def __init__(self, predictor: PredictorInterface):
        self.predictor = predictor

    def execute(self, request: PredictionRequest):
        # 1. Validator
        if not request.domain:
            raise ValueError("Domain missing")
        
        # 2. Feature Builder
        features = self._build_features(request.context)
        
        # 3. Predictor & 4. Confidence Calculator
        raw_pred = self.predictor.predict(features)
        
        # 5. Explanation Builder
        reason, factors = self._build_explanation(raw_pred)
        
        # 6. Recommendation Builder
        recommendation = self._build_recommendation(raw_pred)
        
        # 7. Response
        return {
            "prediction": raw_pred["value"],
            "confidence": raw_pred["confidence"],
            "reason": reason,
            "factors": factors,
            "recommendation": recommendation
        }
        
    def _build_features(self, context):
        return {"speed": 25, "historical_delay": 5}
        
    def _build_explanation(self, raw_pred):
        return "Heavy congestion", ["Vehicle speed", "Traffic", "Historical delay", "Passenger load"]
        
    def _build_recommendation(self, raw_pred):
        if "Delay" in raw_pred["value"]:
            return "Dispatch another vehicle"
        return "No action required"
