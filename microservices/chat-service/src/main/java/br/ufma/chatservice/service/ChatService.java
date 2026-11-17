package br.ufma.chatservice.service;

import br.ufma.chatservice.client.LlmClient;
import br.ufma.chatservice.dto.ChatRequest;
import br.ufma.chatservice.dto.ChatResponse;
import org.springframework.stereotype.Service;

@Service
public class ChatService {

    private final LlmClient llmClient;

    public ChatService(LlmClient llmClient) {
        this.llmClient = llmClient;
    }

    public ChatResponse chat(ChatRequest request) {

        long start = System.nanoTime();

        String response = llmClient.generate(request);

        long elapsed = System.nanoTime() - start;

        return new ChatResponse(
                response,
                elapsed / 1_000_000
        );
    }
}
