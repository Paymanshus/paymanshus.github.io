Setup
Install the CLI
winget install LiveKit.LiveKitCLI
View full instructions in our documentation.

Authenticate
lk cloud auth
Use a starter template (optional)
lk app create \
	--template agent-starter-python <my-app>; cd <my-app>
Create a new deployable agent
lk agent create