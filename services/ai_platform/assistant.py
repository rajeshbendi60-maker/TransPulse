class LlmAdapterInterface:
    def generate_response(self, prompt, context):
        pass

class MockLlmAdapter(LlmAdapterInterface):
    def generate_response(self, prompt, context):
        prompt_lower = prompt.lower()
        if "delayed" in prompt_lower:
            return "Currently, 146 buses are experiencing delays exceeding 5 minutes. The most affected route is 205."
        elif "busiest" in prompt_lower:
            return "The busiest route today is 114 with over 1,200 passengers boarded so far."
        elif "demand tomorrow" in prompt_lower:
            return "Passenger demand is expected to peak at 18,500 tomorrow due to the city festival."
        elif "performance" in prompt_lower:
            return "Driver John Doe holds the highest performance score (98) this week."
        elif "maintenance" in prompt_lower:
            return "Bus #402 requires immediate engine diagnostics."
        return "I am analyzing the TransPulse network. Please specify your operational query."

class AssistantService:
    def __init__(self, adapter: LlmAdapterInterface):
        self.adapter = adapter
        
    def ask(self, prompt, role="Admin"):
        context = {"role": role}
        return self.adapter.generate_response(prompt, context)
