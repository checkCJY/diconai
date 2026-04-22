'use strict';

async function initApp() {
  if (!Auth.getAccessToken()) { Auth.redirectLogin(); return; }

  const user = await Auth.getMe();
  if (!user) {
    Header.renderUser(Auth.getUsername() || '-');
    Menu.showError();
  } else {
    Header.renderUser(user.username);
    Header.showAdminBtn(user.role);
    Menu.render(user.menu_tree);
  }

  SNB.init();
  Header.init();
  Header.updateLastUpdated();
}

initApp();
