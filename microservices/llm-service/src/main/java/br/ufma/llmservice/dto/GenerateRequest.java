package br.ufma.llmservice.dto;

public record GenerateRequest(
        String prompt,
        long delayMs
) {}
