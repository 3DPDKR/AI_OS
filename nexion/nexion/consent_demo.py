"""Local demo: explicit opt-in, two-way communication, and withdrawal."""
import json
from .consent import ConsentStore,ConsentError

def demo():
    store=ConsentStore()
    def make(alias):
        enrollment=store.apply(alias=alias,contact=f"{alias}@example.invalid",
                               scopes={"peer_chat","research"},explicitly_agreed=True)
        store.confirm(enrollment.participant_id,enrollment.confirmation_token)
        return enrollment
    scientist=make("researcher")
    engineer=make("engineer")
    store.send_peer_message(scientist.access_token,engineer.participant_id,
                            "Would you review the offline simulation?")
    store.send_peer_message(engineer.access_token,scientist.participant_id,
                            "Yes, I can review the simulation.")
    messages_before=store.inbox(scientist.access_token)
    store.withdraw(engineer.participant_id,engineer.withdrawal_token)
    try:
        store.send_peer_message(scientist.access_token,engineer.participant_id,"Hello again")
        blocked=False
    except ConsentError:
        blocked=True
    result={"mode":"local simulation, no real external communications",
            "messages_received":len(messages_before),
            "participant_withdrew":True,"post_withdrawal_message_blocked":blocked,
            "external_messages_sent":0,"equipment_activated":0}
    store.close()
    return result

if __name__=="__main__":
    print(json.dumps(demo(),indent=2))
