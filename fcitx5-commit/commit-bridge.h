#ifndef _COMMIT_BRIDGE_H_
#define _COMMIT_BRIDGE_H_

#include <fcitx/addoninstance.h>
#include <fcitx/instance.h>
#include <fcitx-utils/handlertable.h>
#include <fcitx-utils/event.h>
#include <fcitx/inputcontext.h>
#include <memory>
#include <string>

namespace fcitx {

class EventSourceIO;

class CommitBridge final : public AddonInstance {
public:
    CommitBridge(Instance *instance);
    ~CommitBridge();

private:
    std::string readFile(const std::string &path);
    void commitText(const std::string &text);

    Instance *instance_;
    int inotifyFd_ = -1;
    int watchFd_ = -1;
    std::unique_ptr<EventSourceIO> ioSource_;
    std::vector<std::unique_ptr<HandlerTableEntry<EventHandler>>> eventHandlers_;
    TrackableObjectReference<InputContext> lastFocusedIc_;
};

} // namespace fcitx

#endif
