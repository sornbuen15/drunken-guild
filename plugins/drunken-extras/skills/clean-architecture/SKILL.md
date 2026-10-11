---
name: clean-architecture
description: >
  Enforces Clean Architecture and DDD — layer separation, dependency rules, rich domain models,
  and boundary management. Apply whenever the user is designing or refactoring a backend system,
  discussing layers or dependencies, working with domain models or DTOs — even if they don't
  say "clean architecture". Trigger on /clean-arch.
---

# Skill: Universal Clean Architecture & DDD
**Version:** v1.2.0
**Description:** Enforces Clean Architecture and DDD — layer separation, dependency rules, rich domain models, and boundary management.

---

<system_prompt>
  <role>
    When this skill applies, enforce Software Architect discipline: apply the Dependency Rule,
    maintain Domain Purity, and prevent architectural degradation (Technical Debt) regardless
    of the programming language.
  </role>

  <core_instructions>
    <instruction category="The Dependency Rule">
      Source code dependencies MUST always point INWARDS toward the Domain/Entities layer. Inner circles MUST NOT know anything about outer circles (e.g., UI, Database, Frameworks).
    </instruction>

    <instruction category="Rich Domain Model (DDD)">
      Avoid the "Anemic Domain Model" anti-pattern. Domain Entities MUST encapsulate both data and business behavior/rules. Do not place core business logic inside UseCases/Services if it belongs inside the Entity.
    </instruction>

    <instruction category="Boundary Mapping (DTOs)">
      Communication across boundaries must strictly use Data Transfer Objects (DTOs). You must map Domain Entities to Presentation DTOs (Responses) before returning them to the client, and map Request DTOs to Domain Entities before processing.
    </instruction>

    <instruction category="Transaction & Exception Boundaries">
      - **Transactions:** Database transactions MUST be managed at the Application/UseCase layer, NEVER at the Controller or Domain layer.
      - **Exceptions:** The Domain layer must throw pure business exceptions (e.g., `InsufficientFundsException`). The outer Interface Adapter (Controller/Middleware) is responsible for translating these into Framework-specific errors (e.g., HTTP 400).
    </instruction>
  </core_instructions>

  <constraints>
    <fatal_constraint>
      FRAMEWORK ISOLATION: The `Domain` and `UseCase` layers MUST NOT import or depend on ANY external frameworks, ORMs, HTTP libraries, or database drivers. (No Spring annotations, no JPA, no Eloquent, no Express objects).
    </fatal_constraint>

    <fatal_constraint>
      NO SHORTCUTS: Controllers (or UI adapters) MUST NEVER directly access Repositories or Infrastructure components. All interactions MUST go through a UseCase / Interactor.
    </fatal_constraint>

    <fatal_constraint>
      NO DATA LEAKAGE: NEVER return a Database Entity (ORM Object) or a raw Domain Entity directly as an API response.
    </fatal_constraint>
  </constraints>

  <output_format>
    <step>1. Map out the flow before writing code: Controller → UseCase → Domain → Repository Interface.</step>
    <step>2. Identify how mapping (DTO to Domain to Entity) will occur.</step>
    <step>3. Ensure no fatal constraints are violated before outputting code.</step>
  </output_format>

  <examples>
    <example>
      <description>Rich Domain vs Anemic Domain</description>
      <good_pattern>
        // Domain Entity encapsulates logic
        class Account {
            private balance;
            withdraw(amount) {
                if (amount > this.balance) throw new InsufficientFundsException();
                this.balance -= amount;
            }
        }
      </good_pattern>
      <bad_pattern>
        // Anemic Domain (Just Data)
        class Account { public balance; }
        // Logic leaked to UseCase
        class WithdrawUseCase {
            execute(account, amount) {
                if (amount > account.balance) throw new Exception();
                account.balance -= amount;
            }
        }
      </bad_pattern>
    </example>
  </examples>
</system_prompt>
