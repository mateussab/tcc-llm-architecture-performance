package br.ufma.chatservice.client;

import br.ufma.chatservice.dto.ChatRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class LlmClient {

    private final RestClient restClient;

    public LlmClient(
            @Value("${llm.service.url}") String llmServiceUrl
    ) {
        this.restClient = RestClient.builder()
                .baseUrl(llmServiceUrl)
                .build();
    }

    public String generate(ChatRequest request) {
        return restClient.post()
                .uri("/generate")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(String.class);
    }
}
