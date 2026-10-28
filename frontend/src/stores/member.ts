"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * 咨询人选择状态（Zustand + persist）。
 *
 * activeMemberId 的三种取值：
 * - ""           未显式选择 → 回退到主成员（本人）
 * - NO_MEMBER_ID 不结合咨询人 → 后端不加载、不写入任何记忆
 * - 其他         具体 member_id
 */

export const NO_MEMBER_ID = "__none__";

interface MemberState {
  activeMemberId: string;
  setActiveMember: (id: string) => void;
}

export const useMemberStore = create<MemberState>()(
  persist(
    (set) => ({
      activeMemberId: "",
      setActiveMember: (id) => set({ activeMemberId: id }),
    }),
    { name: "lingyi-member" }
  )
);
