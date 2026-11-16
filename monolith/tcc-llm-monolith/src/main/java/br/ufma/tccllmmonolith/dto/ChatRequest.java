package br.ufma.tccllmmonolith.dto;

public record ChatRequest(
        String prompt,
        long delayMs
) {}

