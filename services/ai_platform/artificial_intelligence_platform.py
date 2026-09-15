from .prediction_pipeline import PredictionPipeline, DeterministicPredictor, PredictionRequest
from .assistant import AssistantService, MockLlmAdapter

class AnomalyDetectionEngine:
    def detect_anomalies(self):
        return [
            {"anomaly_type": "GPS Disappeared", "severity": "HIGH", "description": "Vehicle 402 stopped transmitting GPS for 5 minutes.", "resolved": False},
            {"anomaly_type": "Passenger Surge", "severity": "MEDIUM", "description": "Unusual passenger spike at Stop 11.", "resolved": False}
        ]

class ArtificialIntelligencePlatform:
    def __init__(self):
        self.predictor = DeterministicPredictor()
        self.pipeline = PredictionPipeline(self.predictor)
        self.assistant = AssistantService(MockLlmAdapter())
        self.anomaly_engine = AnomalyDetectionEngine()

    def get_dashboard_metrics(self):
        return {
            "eta_accuracy": "94%",
            "predicted_delays": 12,
            "maintenance_risk": "Low",
            "driver_risk": "Medium",
            "operational_health": "Good"
        }

    def predict(self, domain, context):
        request = PredictionRequest(domain, context)
        return self.pipeline.execute(request)

    def ask_assistant(self, prompt, role):
        return self.assistant.ask(prompt, role)

    def get_anomalies(self):
        return self.anomaly_engine.detect_anomalies()

ai_platform = ArtificialIntelligencePlatform()
