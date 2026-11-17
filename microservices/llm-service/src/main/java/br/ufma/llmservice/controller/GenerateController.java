package br.ufma.llmservice.controller;

import br.ufma.llmservice.dto.GenerateRequest;
import br.ufma.llmservice.service.SimulatedLlmService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/generate")
public class GenerateController {

    private final SimulatedLlmService llmService;

    public GenerateController(SimulatedLlmService llmService) {
        this.llmService = llmService;
    }

    @PostMapping
    public String generate(@RequestBody GenerateRequest request) {
        return llmService.generate(
                request.prompt(),
                request.delayMs()
        );
    }
}
