# Zabbix to Matrix Webhook
This Application will server as a webhook between Zabbix and Matrix Chat Romm, it allows:
1. Receive Notification from Zabbix and Structure them in a Defined Format
2. Forward The Message to Matrix Chat Room
3. It can be Enabled/Disabled by sending Command in the chat room
4. Retrieve Notification and Alert History
5. Encryption will be added soon...


![Schema](/misc/Matrix-Zabbix-Webhook.png)


## Setup

### Prerequisites
- Python3.6+
- An Element/Matrix User to Serve as Bot. [Element App Registration](https://app.element.io/#/register)
- A Zabbix Server to be configured 


### This Script webhook is customized to be used in virtual environment and as a Linux Service.


To create a virtual environment in order not to break the OS packages, follow these steps (these steps are in Linux Ubuntu OS):
1. install pip3 packages: </br>
```
sudo apt-get install python3-pip
```

2. install python virtual environment package: </br>
```
sudo apt install python3-venv
```

### Preparing virtual environment
1. First, create your environment with the desired name: </br>
```
python3 -m venv matrix-box
```

2. activate your environment: </br>
```
source box/bin/activate
``` 

(You can further deactivate it via the `deactivate` command.)


### Installation

1. Install dependencies (in your created environment):
   ```
   pip install -r requirements.txt
   ```

2. Set environment variables in `.env` file:
   ```
    MATRIX_HOMESERVER=https://matrix.example.org
    MATRIX_USER_ID=@username:matrix.example.org
    MATRIX_PASSWORD=your_password_here
    MATRIX_ROOM_ID=!roomid:matrix.example.org 
    PORT= (by default it is 5001) 
    DEBUG=(by default it is False)
   ```

## testing matrix-webhook
test your response of Matrix-Webhook via `curl` tool </br>
```bash
curl -X POST http://your-ip-address:5001/webhook  -H "Content-Type: application/json"  -d '{"subject":"Subject-Test","message":"This is a test message","severity":"High","room_id":"!room_id:matrix.org"}'
```

### Zabbix Configuration
1. In Zabbix, go to Alerts > Media types
2. Create a new media type of type "Webhook"
3. Configure the webhook with the following parameters:
    - Name: Matrix Webhook
    - Type: Webhook
    - Media Parameters:
    - Message: {ALERT.MESSAGE}
        - Message:	{ALERT.MESSAGE}
        - Severity:	{TRIGGER.SEVERITY}
        - Subject:	{ALERT.SUBJECT}
        - room_id:	{ALERT.SENDTO}
        - URL:	    http://your-server:5001/webhook (use a User Macro like {$MATRIX_WEBHOOK_URL})
        - Script:
            ```js
            var params = JSON.parse(value);

            var request = new HttpRequest();
            request.addHeader('Content-Type: application/json');

            // Prepare data payload for Flask webhook
            var data = {
                "room_id": params.room_id,
                "subject": params.Subject,
                "message": params.Message,
                "severity": params.Severity
            };

            try {
                var response = request.post(params.URL, JSON.stringify(data));
                var responseData = JSON.parse(response);

                // If Flask returned "ignored"
                if (responseData.status === "ignored") {
                    Zabbix.log(4, 'Matrix notification not sent: Bot disabled');
                    return 'FAILED: Bot is disabled';
                }

                if (responseData.status === "error") {
                    Zabbix.log(4, 'Matrix webhook error: ' + JSON.stringify(responseData.details));
                    return 'FAILED: ' + JSON.stringify(responseData.details);
                }

                return 'OK: ' + JSON.stringify(responseData);
            }
            catch (error) {
                Zabbix.log(4, 'Matrix webhook exception: ' + error);
                throw 'Failed to send message: ' + error;
            }
            ```


            sends payload as following to matrix-webhook:
            ```js
            {
            "room_id": "!room_id:matrix.org",
            "subject": "test Alert",
            "message": "This is a test message",
            "severity": "High"
            }
            ```
4. in Message Templates add Message Template to it
    1. Click **Add** to add a template
    2. Select the event source (e.g., "Trigger")
    3. Select the recovery operation (e.g., "Problem")
    4. Enter a subject like: `Problem: {EVENT.NAME}`
    5. Enter a message like:
        ```
        Problem started at {EVENT.TIME} on {EVENT.DATE}
        Problem name: {EVENT.NAME}
        Host: {HOST.NAME}
        Severity: {TRIGGER.SEVERITY}
        
        Original problem ID: {EVENT.ID}
        {TRIGGER.URL}
        ```
    6. Add another template for recovery operations with an appropriate subject and message 

5. Assign the Media Type to the Proper User.




## Matrix Bot Commands
- `!zabbix_enable` - Enable notifications
- `!zabbix_disable` - Disable notifications
- `!zabbix_status` - Check if notifications are enabled and check number of History that is being held
- `!zabbix_history` - View recent notification history


## API Endpoints
`GET /zabbix_status` - Check the current status
`GET /enable_zabbix` - Enable notifications
`GET /disable_zabbix` - Disable notifications



### To use it as a service:
1. First create a `.service` file in /etc/systemd/system/ (Ubuntu), for instance:
```sh
nano /etc/systemd/system/Zabbix-Matrix-Webhook.service
```

2. Then configure the Service, followed by:
```sh
[Unit]
Description= Description About your Service
After=network.target

[Service]
#User=zabbix  # add user if it needs to be defined in my case not yet
# WorkingDirectory=
ExecStart=/your-path-to-venv-python/matrix-box/bin/python yourpath-to-matrix-webhook/matrix-webhook.py  # Full path of Executer and Python script is 
# Add any other necessary environment variables here if needed
Environment=VAR1=value1
Environment=VAR2=value2

[Install]
WantedBy=multi-user.target
``` 


start your service:
``` systemctl start Zabbix-Matrix-Webhook.service ```

view logs via journalctl:
```  journalctl -u Zabbix-Matrix-Webhook.service ```

reload daemon for changes on service:
``` systemctl daemon-reload ```



