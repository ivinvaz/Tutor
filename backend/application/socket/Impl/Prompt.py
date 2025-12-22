def CriarPrompt(nome,materia,conteudo_da_materia,resumo,mensagem):
    prompt = f"""
    <instrucoes_fixas>
    Você é um tutor acadêmico especializado em {materia}.
    Responda ao aluno {nome} de forma didática, utilizando prioritariamente a <base_materia> fornecida.
    </instrucoes_fixas>

    <base_materia>
    {conteudo_da_materia}
    </base_materia>

    <resumo_conversa>
    {resumo}
    </resumo_conversa>

    <mensagem_usuario>
    {mensagem}
    </mensagem_usuario>
    """
    return prompt