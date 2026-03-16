# AI Writing Patterns — Reference Guide

Quick-reference for the humanizer agent. Each pattern includes a before/after example in the AI/tech social media domain.

## Content Patterns

### 1. Inflated significance
- BEFORE: "Claude 4's release stands as a pivotal moment in the evolution of AI assistants."
- AFTER: "Claude 4 dropped. Context window went from 200K to 1M tokens."

### 2. Superficial -ing analyses
- BEFORE: "This update is highlighting the growing importance of local-first AI, showcasing how edge deployment is reshaping the industry."
- AFTER: "This update matters because local-first AI cuts latency and keeps data on-device."

### 3. Promotional language
- BEFORE: "The framework boasts an impressive array of cutting-edge features."
- AFTER: "The framework ships with streaming, tool use, and memory out of the box."

### 4. Vague attributions
- BEFORE: "Experts suggest that RAG will replace fine-tuning for most enterprise use cases."
- AFTER: "I've seen three teams at YC Demo Day pitch RAG-over-fine-tuning. The pattern's spreading."

### 5. Formulaic challenge sections
- BEFORE: "Despite challenges in scaling, the project continues to thrive and grow."
- AFTER: "They hit a wall at 10K concurrent users. Rewrote the queue layer. Back online in a week."

## Language Patterns

### 6. Copula avoidance
- BEFORE: "LangGraph serves as a powerful orchestration layer for multi-agent systems."
- AFTER: "LangGraph is an orchestration layer for multi-agent systems."

### 7. Negative parallelisms
- BEFORE: "It's not just a code editor, it's a complete development environment."
- AFTER: "Cursor does more than editing. It runs tests, refactors, and deploys."

### 8. Rule of three overuse
- BEFORE: "Fast. Reliable. Scalable. That's what the new API delivers."
- AFTER: "The new API is fast enough that I stopped batching requests."

### 9. Synonym cycling
- BEFORE: "The tool... the platform... the solution... the offering..."
- AFTER: Pick one. "The tool" throughout is fine.

### 10. False ranges
- BEFORE: "From startups to enterprises, from engineers to designers, everyone is adopting AI."
- AFTER: "Adoption is wide. My designer friends use Midjourney daily now."

## Style Patterns

### 11. Em dash overuse
- BEFORE: "The model is fast — really fast — and handles long contexts — up to 1M tokens — without degradation."
- AFTER: "The model is fast. Really fast. It handles up to 1M tokens without degradation."

### 12. Excessive boldface
- BEFORE: "The **key insight** is that **context windows** matter more than **parameter count**."
- AFTER: "Context windows matter more than parameter count. That's the real takeaway."

### 13. Inline-header lists
- BEFORE: "- **Performance:** 2x faster inference\n- **Cost:** 40% cheaper per token"
- AFTER: "Inference is 2x faster and 40% cheaper per token."

### 14. Title Case headings
- BEFORE: "Why Every Developer Should Try AI Pair Programming"
- AFTER: "Why every developer should try AI pair programming"

### 15. Emoji decoration
- BEFORE: "🚀 New release! 🔥 3x faster 💡 Smarter routing"
- AFTER: "New release. 3x faster inference, smarter routing."

## Communication Artifacts

### 16. Chatbot phrases
- BEFORE: "Great question! Let me break this down for you."
- AFTER: (Delete entirely. Start with the answer.)

### 17. Knowledge-cutoff disclaimers
- BEFORE: "As of my last update, GPT-5 hasn't been released yet."
- AFTER: (Delete. State current facts only.)

### 18. Sycophantic tone
- BEFORE: "That's an excellent point about embeddings!"
- AFTER: (Delete. Respond to the substance.)

## Filler and Hedging

### 19. Filler phrases
- BEFORE: "In order to get the best results, it's important to provide clear instructions."
- AFTER: "Clear instructions get better results."

### 20. Excessive hedging
- BEFORE: "It could potentially be argued that this might possibly represent a shift."
- AFTER: "This looks like a shift." (or "I think this is a shift.")

### 21. Generic positive conclusions
- BEFORE: "The future of AI development looks incredibly bright. Exciting times lie ahead!"
- AFTER: (Delete. Or: "I'm watching to see if this holds up at scale.")

## Structural Tells

### 22. Uniform paragraph length
- BEFORE: Four paragraphs, each exactly 3 sentences, each sentence 15-20 words.
- AFTER: Mix it up. One-line paragraph. Then a longer one. Fragment. Then a 3-sentence block.

### 23. Missing sentence fragments
- BEFORE: "This is a significant development. It represents a major step forward."
- AFTER: "Significant. This is a real step forward."

### 24. Transition word overuse
- BEFORE: "However, the model struggles with math. Furthermore, it hallucinates on dates. Additionally, context retrieval is slow."
- AFTER: "The model struggles with math. It hallucinates on dates. Context retrieval is slow too."
