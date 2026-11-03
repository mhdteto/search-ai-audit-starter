# Measurement protocol

Write the protocol before collecting responses. This is an operational approach, not a validated universal measurement standard.

## Scope and conditions

Assign an entity_id and a measurement_id. Freeze the prompt set and define the audience, market and language. Record engine, model if disclosed, interface (consumer UI versus API), date/time with timezone, search/grounding mode, personalization/account conditions where known, and the identity aliases accepted by the reviewer. API behavior must not be presented as identical to a consumer product.

Do not mix prompt versions, failed requests or incompatible conditions into a pooled trend. Decide the intended repeats in advance; repeating an identical prompt does not make its answers statistically independent.

## Prompt families

Use a documented mixture of identity, expertise/category, comparison, selection and verification questions. Store the wording and rationale. Avoid leading prompts that instruct the model to endorse the subject. Translate for local intent and document the change; a translation is not necessarily a matched experimental condition.

## Capture and review

Save full answers and visible cited URLs with a stable artifact path. Record whether collection succeeded. A human checks entity match, individual factual claims and whether a citation actually supports the associated statement. Record uncertainty rather than forcing a binary verdict.

## Reportable diagnostics

- **Presence rate:** eligible successful answers mentioning the intended entity / eligible successful answers. State the counts, prompt set and dates alongside the percentage. Exclude namesakes after review and disclose exclusions.
- **Citation rate:** eligible successful answers citing at least one agreed target source / eligible successful answers. Define target sources and whether citations are clickable or merely named.
- **Accuracy findings:** report supported, contradicted and unverified claim counts with the review rubric and evidence. An unverified claim is not automatically false.
- **Peer comparison:** show counts within the same sampled conditions. Call this a comparison of the sample, not a market-wide share of voice.

A failed request has no presence verdict. An uncited answer may still be factually accurate. A cited answer may be wrong. Missing model metadata stays unknown.

## Interpretation

Keep engine-level and market/language-level results separate. Record collection window, sample size, limitations and changes to the protocol. If uncertainty intervals are used, explain their assumptions and limitations; repeated prompts and related answers can violate independence assumptions. Do not combine these diagnostics into an allegedly universal authority score.

## Publication gate

Publish only material that can be shared lawfully and with appropriate consent. Remove confidential and unnecessary personal data. Make the protocol, exclusions and evidence access limitations clear. If no measurements were collected, label the artifact a template or synthetic demonstration.

Templates: [baseline log](../templates/baseline-log.csv) and [source inventory](../templates/source-inventory.csv). Website: [research principles](https://mohammedteto.com/research/).
