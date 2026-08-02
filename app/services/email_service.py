import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config.settings import (
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


class EmailService:

    @property
    def configurado(self) -> bool:
        return bool(SMTP_USER and SMTP_PASSWORD and SMTP_HOST)

    def enviar_reset_senha(self, destinatario: str, nome: str, reset_url: str) -> None:
        if not self.configurado:
            raise RuntimeError("SMTP não configurado. Defina SMTP_USER e SMTP_PASSWORD no .env")

        assunto = "Redefinir sua senha — PulseDesk"
        texto = (
            f"Olá, {nome}!\n\n"
            "Recebemos uma solicitação para redefinir a senha da sua conta PulseDesk.\n"
            f"Acesse o link abaixo (válido por 1 hora):\n\n{reset_url}\n\n"
            "Se você não solicitou isso, ignore este e-mail.\n\n"
            "Equipe PulseDesk"
        )
        html = f"""\
<!DOCTYPE html>
<html lang="pt-BR">
<body style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:560px;margin:0 auto;padding:24px;">
  <h2 style="color:#0d9488;margin:0 0 16px;">Redefinir senha</h2>
  <p>Olá, <strong>{nome}</strong>!</p>
  <p>Recebemos uma solicitação para redefinir a senha da sua conta PulseDesk.</p>
  <p style="margin:24px 0;">
    <a href="{reset_url}"
       style="background:#0d9488;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block;">
      Redefinir minha senha
    </a>
  </p>
  <p style="font-size:13px;color:#6b7280;">Este link expira em 1 hora. Se o botão não funcionar, copie e cole no navegador:<br>{reset_url}</p>
  <p style="font-size:13px;color:#6b7280;margin-top:24px;">Se você não solicitou isso, ignore este e-mail.</p>
</body>
</html>"""

        self._enviar(destinatario, assunto, texto, html)

    def _enviar(self, destinatario: str, assunto: str, texto: str, html: str) -> None:
        remetente = SMTP_FROM_EMAIL or SMTP_USER
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"{SMTP_FROM_NAME} <{remetente}>"
        msg["To"] = destinatario
        msg.attach(MIMEText(texto, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(remetente, [destinatario], msg.as_string())
            logger.info("E-mail enviado para %s", destinatario)
        except smtplib.SMTPException as exc:
            logger.exception("Falha ao enviar e-mail para %s", destinatario)
            raise RuntimeError("Não foi possível enviar o e-mail de recuperação") from exc
