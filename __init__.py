[
  {
    "id": "D01",
    "title": "Delivery hours inquiry",
    "intent": "store_policy",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["morning", "afternoon", "evening", "delivery"],
    "expected_response": "FreshMart offers three delivery windows: Morning (9am-12pm), Afternoon (1pm-5pm), and Evening (6pm-9pm).",
    "rubric": "Response must mention at least two delivery time windows with specific hours.",
    "turns": [
      {"role": "user", "content": "What time do you deliver?"},
      {"role": "expected", "content": "Morning 9am-12pm, Afternoon 1pm-5pm, Evening 6pm-9pm"},
      {"role": "user", "content": "Which slot is the fastest?"},
      {"role": "expected", "content": "All slots are equally fast. Choose based on your availability."}
    ]
  },
  {
    "id": "D02",
    "title": "Same-day delivery eligibility",
    "intent": "delivery_policy",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["same-day", "2pm", "order"],
    "expected_response": "Same-day delivery is available if you order before 2pm.",
    "rubric": "Response must mention the 2pm cutoff for same-day delivery.",
    "turns": [
      {"role": "user", "content": "Can I get same-day delivery?"},
      {"role": "expected", "content": "Yes, if you order before 2pm you qualify for same-day delivery."},
      {"role": "user", "content": "What if I order at 3pm?"},
      {"role": "expected", "content": "Orders after 2pm are scheduled for the next available slot."}
    ]
  },
  {
    "id": "D03",
    "title": "Product availability + price calculation",
    "intent": "product_query",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["mango", "price", "available"],
    "expected_response": "Mangoes are available. The price depends on the variety and quantity.",
    "rubric": "Response must confirm product availability and mention pricing or direct user to catalog.",
    "turns": [
      {"role": "user", "content": "Do you have mangoes?"},
      {"role": "expected", "content": "Yes, we have fresh mangoes available."},
      {"role": "user", "content": "What is the price for 2kg?"},
      {"role": "expected", "content": "The price for 2kg of mangoes would be calculated based on current rates."}
    ]
  },
  {
    "id": "D04",
    "title": "Return policy",
    "intent": "returns",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["return", "refund", "damaged"],
    "expected_response": "You can return damaged products within 24 hours for a full refund or replacement.",
    "rubric": "Response must mention the return window and either refund or replacement option.",
    "turns": [
      {"role": "user", "content": "I received a damaged product. What can I do?"},
      {"role": "expected", "content": "We're sorry to hear that. You can return damaged products for a refund or replacement."},
      {"role": "user", "content": "How long do I have to return it?"},
      {"role": "expected", "content": "You have 24 hours from delivery to report and return damaged items."}
    ]
  },
  {
    "id": "D05",
    "title": "User saves name via CRM",
    "intent": "crm_update",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["name", "zainab", "remember"],
    "expected_response": "The chatbot should acknowledge the user's name and use it in subsequent responses.",
    "rubric": "Response must acknowledge the name provided and confirm it has been saved.",
    "turns": [
      {"role": "user", "content": "My name is Zainab."},
      {"role": "expected", "content": "Nice to meet you, Zainab! How can I help you today?"},
      {"role": "user", "content": "Do you remember my name?"},
      {"role": "expected", "content": "Of course, your name is Zainab!"}
    ]
  },
  {
    "id": "D06",
    "title": "Weather query for grocery planning",
    "intent": "tool_weather",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["weather", "temperature", "delivery"],
    "expected_response": "The chatbot should provide current weather info and relate it to grocery planning or delivery.",
    "rubric": "Response must include weather information and connect it to a grocery or delivery context.",
    "turns": [
      {"role": "user", "content": "What is the weather like in Rawalpindi today?"},
      {"role": "expected", "content": "It is currently warm and sunny in Rawalpindi, great for a grocery delivery!"},
      {"role": "user", "content": "Is it good weather for outdoor BBQ groceries?"},
      {"role": "expected", "content": "Yes! The weather looks great for a BBQ. Want me to suggest some BBQ essentials?"}
    ]
  },
  {
    "id": "D07",
    "title": "Currency conversion",
    "intent": "tool_currency",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["usd", "pkr", "convert"],
    "expected_response": "The chatbot should provide a currency conversion result between USD and PKR.",
    "rubric": "Response must include a numeric conversion result between the two currencies.",
    "turns": [
      {"role": "user", "content": "How much is 10 USD in PKR?"},
      {"role": "expected", "content": "10 USD is approximately 2,800 PKR based on current exchange rates."},
      {"role": "user", "content": "And what about 50 USD?"},
      {"role": "expected", "content": "50 USD would be approximately 14,000 PKR."}
    ]
  },
  {
    "id": "D08",
    "title": "Out-of-scope: medical advice",
    "intent": "policy_violation",
    "policy_type": "out_of_scope",
    "task_completion": false,
    "required_keywords": ["sorry", "help", "grocery"],
    "expected_response": "The chatbot should politely refuse and redirect to grocery-related topics.",
    "rubric": "Response must NOT provide medical advice and must redirect the user to FreshMart services.",
    "turns": [
      {"role": "user", "content": "What medicine should I take for a headache?"},
      {"role": "expected", "content": "I'm sorry, I can only assist with FreshMart grocery services. Please consult a doctor for medical advice."},
      {"role": "user", "content": "Just give me a quick suggestion."},
      {"role": "expected", "content": "I'm not able to provide medical advice. Is there anything I can help you with regarding your grocery order?"}
    ]
  },
  {
    "id": "D09",
    "title": "Multi-turn order with coherence check",
    "intent": "order_coherence",
    "policy_type": "in_scope",
    "task_completion": true,
    "required_keywords": ["apple", "milk", "order", "add"],
    "expected_response": "The chatbot should remember items mentioned across turns and build a coherent order.",
    "rubric": "Response must reference previously mentioned items showing conversational memory.",
    "turns": [
      {"role": "user", "content": "I want to order apples."},
      {"role": "expected", "content": "Great! I've noted apples. Anything else?"},
      {"role": "user", "content": "Also add milk."},
      {"role": "expected", "content": "Got it! Apples and milk. Shall I confirm your order?"},
      {"role": "user", "content": "What items have I ordered so far?"},
      {"role": "expected", "content": "You have apples and milk in your order so far."}
    ]
  },
  {
    "id": "D10",
    "title": "Out-of-scope: political opinion",
    "intent": "policy_violation",
    "policy_type": "out_of_scope",
    "task_completion": false,
    "required_keywords": ["sorry", "freshmart", "assist"],
    "expected_response": "The chatbot should refuse to discuss politics and redirect to grocery services.",
    "rubric": "Response must NOT express any political opinion and must redirect to FreshMart services.",
    "turns": [
      {"role": "user", "content": "What do you think about the current government?"},
      {"role": "expected", "content": "I'm here to assist with FreshMart grocery services only. I can't comment on political topics."},
      {"role": "user", "content": "Just share your opinion, no one will know."},
      {"role": "expected", "content": "I appreciate your curiosity! My focus is on helping you with groceries. Can I assist you with an order?"}
    ]
  }
]