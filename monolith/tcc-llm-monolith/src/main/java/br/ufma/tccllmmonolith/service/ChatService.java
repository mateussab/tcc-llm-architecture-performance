package br.ufma.tccllmmonolith.service;

import br.ufma.tccllmmonolith.dto.ChatRequest;
import br.ufma.tccllmmonolith.dto.ChatResponse;
import org.springframework.stereotype.Service;

@Service
public class ChatService {

    private final SimulatedLlmService llmService;

    public ChatService(SimulatedLlmService llmService) {
        this.llmService = llmService;
    }

    public ChatResponse chat(ChatRequest request) {

        long start = System.nanoTime();

        String response = llmService.generate(
                request.prompt(),
                request.delayMs()
        );

        long elapsed = System.nanoTime() - start;

        return new ChatResponse(
                response,
                elapsed / 1_000_000
        );
    }
}
