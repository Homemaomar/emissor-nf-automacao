from envio.whatsapp_sender import WhatsAppSender

sender = WhatsAppSender()
sender.iniciar()

sender.enviar_mensagem("8799196825", "Meu emissor de notas fiscais envia whatsapp!! UhUuuuu! 🚀")

input("Pressione ENTER para finalizar...")
sender.finalizar()