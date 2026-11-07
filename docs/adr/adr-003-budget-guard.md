# ADR-003: Budget Guard — quinto control de seguridad (propio)

## Contexto

El SDK de Strands no incluye ningun mecanismo nativo de presupuesto de tokens. El resultado
del swarm expone `accumulated_usage["totalTokens"]` pero no lo usa para detener la ejecucion.

Adicionalmente, `Swarm.stream_async` (swarm.py ~465) recrea `self.state = SwarmState(...)` al
inicio de cada invocacion. Esto invalida cualquier monkey-patch colocado sobre `swarm.state`
despues de la construccion: el wrapper se descarta antes de la primera evaluacion del ciclo.
Este comportamiento fue verificado leyendo el codigo fuente de strands-agents==1.64.0 y es un
hallazgo publicable del benchmark.

## Decision

Implementar `BudgetAwareSwarm(Swarm)` como **subclase** de `Swarm` que sobreescribe `stream_async`,
verificando el acumulado de tokens en cada iteracion antes de ceder el control al caller.
La subclase emite `logger.debug("budget_exceeded")` antes de retornar, de modo que el
`StopReasonInterceptor` lo captura igual que los limites nativos del SDK.

Este diseno sobrevive la re-creacion de `SwarmState` porque el override vive en la clase,
no en la instancia de estado.

## Alternativa considerada

**Wrapper post-construccion**: reemplazar `swarm.state.should_continue` despues de que
`SwarmFactory` construye el swarm. Descartado porque `Swarm.stream_async` recrea `self.state`
al inicio de cada invocacion (swarm.py ~465), descartando el wrapper antes de que se evalúe.
Esta era la decision original (v1 de este ADR); fue invalidada por revision cruzada contra
el codigo fuente del SDK instalado.

## Trade-offs

| Aspecto | Subclase BudgetAwareSwarm | Wrapper post-construccion |
|---|---|---|
| Sobrevive reset de SwarmState | si — override en clase | No — descartado por stream_async |
| Correccion con SDK v1.64.0 | Funciona | No funciona |
| Invasividad de imports | SwarmFactory crea BudgetAwareSwarm en vez de Swarm | Ninguna |
| Pruebas unitarias | Instanciable como Swarm normal | Mock directo |
| Compatibilidad con SDK updates | Si stream_async cambia firma, hay que adaptar | Solo depende de firma de should_continue |
